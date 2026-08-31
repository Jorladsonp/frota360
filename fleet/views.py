import csv
import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import (
    CashEntryForm, ContractForm, DriverForm, FinancingForm, FixedCostForm, FuelingForm, MaintenanceForm, MaintenancePlanForm,
    OccurrenceForm, ProductionForm, RemunerationRuleForm, StopForm, TireExpenseForm,
    TripFinishForm, TripPlanForm, TripStartForm, TripStartPlannedForm, TruckForm, VehicleChecklistForm,
)
from .models import (
    AuditLog, CashEntry, Company, Contract, Driver, FixedCost, Fueling, Maintenance, MaintenancePlan, Occurrence,
    Production, Remuneration, RemunerationRule, Stop, TireExpense, Trip, Truck,
    UserProfile,
    VehicleChecklist,
)
from .permissions import company_for, driver_required, manager_required, profile_for
from .services import calculate_driver_remuneration, calculate_fixed_cost_allocation, month_bounds, production_allocation, prorated_monthly_amount, remuneration_truck_allocation, truck_costs


def current_company(user):
    company = company_for(user)
    if company:
        return company
    if user.is_superuser:
        return Company.objects.filter(active=True).first()
    return None


@require_GET
def pwa_service_worker(request):
    """Serve the worker at the site root so the driver PWA can cover its routes."""
    response = HttpResponse(
        """const CACHE = 'frota360-static-v2';
const ASSETS = ['/static/fleet/app.css', '/static/fleet/app.js', '/static/fleet/pwa-icon.svg'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('frota360-static-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
  if (new URL(request.url).pathname.startsWith('/static/')) {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(request, copy));
      return response;
    }).catch(() => caches.match(request).then(cached => cached || caches.match(new URL(request.url).pathname))));
  }
});""",
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def snapshot(instance):
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, timedelta):
            value = str(value)
        elif hasattr(value, "storage") and hasattr(value, "name"):
            value = value.name
        elif hasattr(value, "pk"):
            value = value.pk
        data[field.name] = value
    return data


def audit(user, instance, action, before=None, reason=""):
    company = getattr(instance, "company", None) or current_company(user)
    if not company:
        return
    AuditLog.objects.create(
        company=company, user=user, action=action, model_name=instance.__class__.__name__,
        object_id=str(instance.pk), reason=reason, before_data=before or {}, after_data=snapshot(instance),
    )


def parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else fallback
    except (TypeError, ValueError):
        return fallback


def shift_month(value, months):
    """Move a date by whole calendar months while keeping it on day one."""
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def filter_period(request):
    today = timezone.localdate()
    default_start = today.replace(day=1) - timedelta(days=150)
    start, end = parse_date(request.GET.get("start"), default_start), parse_date(request.GET.get("end"), today)
    return (end, start) if start > end else (start, end)


def operational_filter_context(request, company, default_days=30):
    today = timezone.localdate()
    start = parse_date(request.GET.get("start"), today - timedelta(days=default_days - 1))
    end = parse_date(request.GET.get("end"), today)
    if start > end:
        start, end = end, start
    selected = {key: request.GET.get(key, "") for key in ("truck", "driver", "contract", "status", "fuel_type", "city", "state", "tank_full")}
    return {
        "start": start,
        "end": end,
        "trucks": Truck.objects.filter(company=company),
        "drivers": Driver.objects.filter(company=company, status=Driver.ACTIVE),
        "contracts": Contract.objects.filter(company=company),
        "trip_statuses": Trip.STATUS_CHOICES,
        "fuel_types": Truck.FUEL_CHOICES,
        **{f"selected_{key}": value for key, value in selected.items()},
    }


def filtered_trips(company, filters):
    queryset = Trip.objects.filter(company=company).filter(
        Q(started_at__date__range=(filters["start"], filters["end"])) |
        Q(status=Trip.PLANNED, created_at__date__range=(filters["start"], filters["end"]))
    ).select_related("truck", "driver", "contract")
    for field in ("truck", "driver", "contract", "status"):
        if filters[f"selected_{field}"]:
            lookup = f"{field}_id" if field != "status" else field
            queryset = queryset.filter(**{lookup: filters[f"selected_{field}"]})
    return queryset


def operational_chart_data(trips, start, end):
    status_rows = {row["status"]: row["total"] for row in trips.values("status").annotate(total=Count("id"))}
    labels, dates, trip_counts, distance = [], [], [], []
    cursor = start
    while cursor <= end:
        day = trips.filter(started_at__date=cursor)
        labels.append(cursor.strftime("%d/%m"))
        dates.append(cursor.isoformat())
        trip_counts.append(day.count())
        distance.append(float(day.aggregate(total=Sum("distance_km"))["total"] or 0))
        cursor += timedelta(days=1)
    truck_rows = list(trips.filter(status=Trip.FINISHED).values("truck_id", "truck__identification").annotate(distance=Sum("distance_km"), trips=Count("id")).order_by("-distance", "truck__identification"))
    driver_rows = list(trips.filter(status=Trip.FINISHED).values("driver_id", "driver__name").annotate(distance=Sum("distance_km"), trips=Count("id")).order_by("-distance", "driver__name"))
    return {
        "status": {"labels": [label for key, label in Trip.STATUS_CHOICES if status_rows.get(key)], "keys": [key for key, _ in Trip.STATUS_CHOICES if status_rows.get(key)], "values": [status_rows[key] for key, _ in Trip.STATUS_CHOICES if status_rows.get(key)]},
        "daily": {"labels": labels, "dates": dates, "trips": trip_counts, "distance": distance},
        "trucks": {"labels": [row["truck__identification"] for row in truck_rows], "ids": [row["truck_id"] for row in truck_rows], "distance": [float(row["distance"] or 0) for row in truck_rows], "trips": [row["trips"] for row in truck_rows]},
        "drivers": {"labels": [row["driver__name"] for row in driver_rows], "ids": [row["driver_id"] for row in driver_rows], "distance": [float(row["distance"] or 0) for row in driver_rows]},
    }


def fuel_chart_data(fuelings, start, end):
    labels, starts, ends, amount, liters = [], [], [], [], []
    cursor = start.replace(day=1)
    while cursor <= end:
        month_end = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        period_start, period_end = max(start, cursor), min(end, month_end)
        month_fuelings = fuelings.filter(fueled_at__date__range=(period_start, period_end))
        labels.append(cursor.strftime("%m/%Y"))
        starts.append(period_start.isoformat())
        ends.append(period_end.isoformat())
        amount.append(float(month_fuelings.aggregate(total=Sum("total_amount"))["total"] or 0))
        liters.append(float(month_fuelings.aggregate(total=Sum("liters"))["total"] or 0))
        cursor = month_end + timedelta(days=1)
    trucks = list(fuelings.values("truck_id", "truck__identification").annotate(amount=Sum("total_amount"), liters=Sum("liters")).order_by("-amount", "truck__identification"))
    cities = list(fuelings.values("city", "state").annotate(amount=Sum("total_amount")).order_by("-amount", "city")[:8])
    return {
        "monthly": {"labels": labels, "starts": starts, "ends": ends, "amount": amount, "liters": liters},
        "trucks": {"labels": [row["truck__identification"] for row in trucks], "ids": [row["truck_id"] for row in trucks], "amount": [float(row["amount"] or 0) for row in trucks], "liters": [float(row["liters"] or 0) for row in trucks]},
        "cities": {"labels": [f'{row["city"]}/{row["state"]}' for row in cities], "cities": [row["city"] for row in cities], "amount": [float(row["amount"] or 0) for row in cities]},
    }


def dashboard_filter_context(request, company):
    start, end = filter_period(request)
    trucks = Truck.objects.filter(company=company)
    drivers = Driver.objects.filter(company=company)
    contracts = Contract.objects.filter(company=company)
    selected_truck = request.GET.get("truck", "")
    selected_driver = request.GET.get("driver", "")
    selected_contract = request.GET.get("contract", "")
    selected_fuel_type = request.GET.get("fuel_type", "")
    selected_fleet_status = request.GET.get("fleet_status", "")
    if selected_truck:
        trucks = trucks.filter(pk=selected_truck)
    if selected_driver:
        drivers = drivers.filter(pk=selected_driver)
    if selected_contract:
        contracts = contracts.filter(pk=selected_contract)
    if selected_fleet_status in (Truck.OPERATING, Truck.MAINTENANCE, Truck.INACTIVE):
        trucks = trucks.filter(status=selected_fleet_status)
    return {
        "start": start, "end": end, "trucks": Truck.objects.filter(company=company), "drivers": Driver.objects.filter(company=company),
        "contracts": Contract.objects.filter(company=company), "selected_truck": selected_truck, "selected_driver": selected_driver,
        "selected_contract": selected_contract, "selected_fuel_type": selected_fuel_type, "selected_fleet_status": selected_fleet_status, "fleet_statuses": Truck.STATUS_CHOICES, "fuel_types": Truck.FUEL_CHOICES, "city": request.GET.get("city", ""), "state": request.GET.get("state", ""),
    }, (trucks, drivers, contracts)


def dashboard_metrics(company, start, end, truck_ids=None, driver_ids=None, contract_ids=None, city="", state="", fuel_type=""):
    trip_qs = Trip.objects.filter(company=company, status=Trip.FINISHED, started_at__date__gte=start, started_at__date__lte=end)
    fuel_qs = Fueling.objects.filter(company=company, fueled_at__date__gte=start, fueled_at__date__lte=end)
    production_qs = Production.objects.filter(
        company=company,
        competence__gte=start,
        competence__lte=end,
        status=Production.APPROVED,
    )
    if truck_ids:
        trip_qs = trip_qs.filter(truck_id__in=truck_ids)
        fuel_qs = fuel_qs.filter(truck_id__in=truck_ids)
        production_qs = production_qs.filter(Q(truck_id__in=truck_ids) | Q(truck__isnull=True))
    if driver_ids:
        trip_qs = trip_qs.filter(driver_id__in=driver_ids)
        fuel_qs = fuel_qs.filter(Q(driver_id__in=driver_ids) | Q(driver__isnull=True))
        production_qs = production_qs.filter(Q(driver_id__in=driver_ids) | Q(driver__isnull=True))
    if contract_ids:
        trip_qs = trip_qs.filter(contract_id__in=contract_ids)
        production_qs = production_qs.filter(contract_id__in=contract_ids)
    if city:
        fuel_qs = fuel_qs.filter(city__icontains=city)
    if state:
        fuel_qs = fuel_qs.filter(state__iexact=state)
    if fuel_type:
        fuel_qs = fuel_qs.filter(fuel_type=fuel_type)
    if truck_ids and not (driver_ids or contract_ids or city or state):
        allocation = production_allocation(company, start, end)
        revenue = sum((allocation.get(truck_id, Decimal("0")) for truck_id in truck_ids), Decimal("0"))
    else:
        revenue = production_qs.aggregate(total=Sum("realized_value"))["total"] or Decimal("0")
    fuel = fuel_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    liters = fuel_qs.aggregate(total=Sum("liters"))["total"] or Decimal("0")
    maintenance = Maintenance.objects.filter(company=company, date__gte=start, date__lte=end)
    tires = TireExpense.objects.filter(company=company, date__gte=start, date__lte=end)
    if truck_ids:
        maintenance = maintenance.filter(truck_id__in=truck_ids)
        tires = tires.filter(truck_id__in=truck_ids)
    maintenance_value = maintenance.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    tires_value = tires.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    financing = Decimal("0")
    financing_qs = company.financing_set.select_related("truck").all()
    for item in financing_qs:
        if truck_ids and item.truck_id not in truck_ids:
            continue
        if item.truck.financial_status == Truck.FINANCED and item.start_date and item.start_date <= end and (not item.expected_end_date or item.expected_end_date >= start):
            financing += prorated_monthly_amount(item.monthly_payment, start, end, item.start_date, item.expected_end_date)
    remunerations = Remuneration.objects.filter(company=company, competence__gte=start, competence__lte=end)
    if driver_ids:
        remunerations = remunerations.filter(driver_id__in=driver_ids)
    remuneration_allocation = remuneration_truck_allocation(company, start, end, driver_ids)
    remuneration = sum((remuneration_allocation.get(truck_id, Decimal("0")) for truck_id in truck_ids), Decimal("0")) if truck_ids else sum(remuneration_allocation.values(), Decimal("0"))
    fixed_costs = FixedCost.objects.filter(company=company, valid_from__lte=end, active=True).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start))
    if truck_ids:
        fixed_costs = fixed_costs.filter(Q(truck_id__in=truck_ids) | Q(truck__isnull=True))
    fixed_value = sum(
        (
            prorated_monthly_amount(item.monthly_amount, start, end, item.valid_from, item.valid_until)
            for item in fixed_costs
        ),
        Decimal("0"),
    )
    total_cost = fuel + maintenance_value + tires_value + financing + fixed_value + remuneration
    distance = trip_qs.aggregate(total=Sum("distance_km"))["total"] or Decimal("0")
    hours = sum((trip.duration.total_seconds() for trip in trip_qs if trip.duration), 0) / 3600
    km_l_values = list(fuel_qs.exclude(km_per_liter__isnull=True).values_list("km_per_liter", flat=True))
    avg_km_l = sum(km_l_values, Decimal("0")) / len(km_l_values) if km_l_values else Decimal("0")
    return {
        "revenue": revenue, "fuel": fuel, "liters": liters, "maintenance": maintenance_value, "tires": tires_value,
        "financing": financing, "fixed": fixed_value, "remuneration": remuneration, "total_cost": total_cost,
        "result": revenue - total_cost, "distance": distance, "hours": hours, "avg_km_l": avg_km_l,
        "cost_per_km": total_cost / distance if distance else Decimal("0"), "fuel_cost_per_km": fuel / distance if distance else Decimal("0"),
        "commissions": remunerations.aggregate(total=Sum("commission_amount"))["total"] or Decimal("0"),
        "bonuses": sum((r.km_bonus + r.trips_bonus + r.other_bonus for r in remunerations), Decimal("0")),
    }


def monthly_chart_data(company, start, end, truck_ids=None, driver_ids=None, contract_ids=None, city="", state="", fuel_type=""):
    labels, revenue, costs, result, consumption = [], [], [], [], []
    cursor = start.replace(day=1)
    while cursor <= end:
        month_end = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        month_start = max(start, cursor)
        month_end = min(end, month_end)
        metric = dashboard_metrics(company, month_start, month_end, truck_ids=truck_ids, driver_ids=driver_ids, contract_ids=contract_ids, city=city, state=state, fuel_type=fuel_type)
        labels.append(cursor.strftime("%b/%y"))
        revenue.append(float(metric["revenue"]))
        costs.append(float(metric["total_cost"]))
        result.append(float(metric["result"]))
        consumption.append(float(metric["avg_km_l"]))
        cursor = month_end + timedelta(days=1)
    starts, ends = [], []
    cursor = start.replace(day=1)
    while cursor <= end:
        month_end = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        starts.append(max(start, cursor).isoformat())
        ends.append(min(end, month_end).isoformat())
        cursor = month_end + timedelta(days=1)
    return {"labels": labels, "revenue": revenue, "costs": costs, "result": result, "consumption": consumption, "starts": starts, "ends": ends}


def breakdown_chart_data(company, start, end, truck_ids=None, driver_ids=None, contract_ids=None, city="", state="", fuel_type=""):
    trucks = Truck.objects.filter(company=company)
    if truck_ids:
        trucks = trucks.filter(pk__in=truck_ids)
    if driver_ids:
        driver_trucks = Trip.objects.filter(company=company, driver_id__in=driver_ids).values_list("truck_id", flat=True)
        trucks = trucks.filter(pk__in=driver_trucks)
    if contract_ids:
        contract_trucks = Trip.objects.filter(company=company, contract_id__in=contract_ids).values_list("truck_id", flat=True)
        trucks = trucks.filter(pk__in=contract_trucks)
    truck_labels, result_values, km_l_values, maintenance_values = [], [], [], []
    for truck in trucks:
        metric = dashboard_metrics(company, start, end, [truck.pk], driver_ids, contract_ids, city, state, fuel_type)
        truck_labels.append(truck.identification)
        result_values.append(float(metric["result"]))
        km_fuel = Fueling.objects.filter(company=company, truck=truck, fueled_at__date__range=(start, end), tank_full=True).exclude(km_per_liter__isnull=True)
        if fuel_type:
            km_fuel = km_fuel.filter(fuel_type=fuel_type)
        km_l_values.append(float(km_fuel.aggregate(value=Avg("km_per_liter"))["value"] or 0))
        maintenance_values.append(float(Maintenance.objects.filter(company=company, truck=truck, date__range=(start, end)).aggregate(value=Sum("amount"))["value"] or 0))
    production = Production.objects.filter(company=company, competence__range=(start, end)).exclude(status=Production.CANCELLED)
    if contract_ids:
        production = production.filter(contract_id__in=contract_ids)
    if truck_ids:
        production = production.filter(Q(truck_id__in=truck_ids) | Q(truck__isnull=True))
    production_rows = list(production.values("contract_id", "contract__code").annotate(value=Sum("realized_value")).order_by("contract__code"))
    remuneration = Remuneration.objects.filter(company=company, competence__range=(start, end))
    if driver_ids:
        remuneration = remuneration.filter(driver_id__in=driver_ids)
    remuneration_rows = list(remuneration.values("driver_id", "driver__name").annotate(value=Sum("total_amount")).order_by("driver__name"))
    return {"truck_labels": truck_labels, "truck_ids": list(trucks.values_list("pk", flat=True)), "result_values": result_values, "km_l_values": km_l_values, "maintenance_values": maintenance_values, "contract_labels": [row["contract__code"] for row in production_rows], "contract_ids": [row["contract_id"] for row in production_rows], "production_values": [float(row["value"] or 0) for row in production_rows], "driver_labels": [row["driver__name"] for row in remuneration_rows], "driver_ids": [row["driver_id"] for row in remuneration_rows], "remuneration_values": [float(row["value"] or 0) for row in remuneration_rows]}


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    profile = profile_for(request.user)
    if request.user.is_superuser or (profile and profile.role == UserProfile.MANAGER):
        return redirect("dashboard")
    if profile and profile.role == UserProfile.DRIVER:
        return redirect("driver_dashboard")
    messages.error(request, "Seu usuário ainda não possui um perfil de frota.")
    return redirect("login")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            profile = profile_for(user)
            if user.is_superuser or (profile and profile.role == UserProfile.MANAGER):
                return redirect("dashboard")
            return redirect("driver_dashboard")
        messages.error(request, "Usuário ou senha inválidos.")
    return render(request, "registration/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@manager_required
def dashboard(request):
    company = current_company(request.user)
    if not company:
        messages.error(request, "Nenhuma empresa ativa foi configurada.")
        return render(request, "fleet/empty.html", {"title": "Empresa não configurada"})
    filters, selected = dashboard_filter_context(request, company)
    trucks, drivers, contracts = selected
    truck_ids = list(trucks.values_list("id", flat=True)) if (filters["selected_truck"] or filters["selected_fleet_status"]) else None
    driver_ids = list(drivers.values_list("id", flat=True)) if filters["selected_driver"] else None
    contract_ids = list(contracts.values_list("id", flat=True)) if filters["selected_contract"] else None
    metric = dashboard_metrics(company, filters["start"], filters["end"], truck_ids, driver_ids, contract_ids, filters["city"], filters["state"], filters["selected_fuel_type"])
    all_trucks = Truck.objects.filter(company=company)
    fleet_health_trucks = all_trucks
    if filters["selected_fleet_status"] in (Truck.OPERATING, Truck.MAINTENANCE, Truck.INACTIVE):
        fleet_health_trucks = fleet_health_trucks.filter(status=filters["selected_fleet_status"])
    repeated_maintenance = Maintenance.objects.filter(company=company, date__gte=filters["start"], date__lte=filters["end"]).values("truck_id", "maintenance_type").annotate(total=Count("id")).filter(total__gt=1).count()
    context = {**filters, "company": company, "metrics": metric, "chart_data": json.dumps(monthly_chart_data(company, filters["start"], filters["end"], truck_ids, driver_ids, contract_ids, filters["city"], filters["state"], filters["selected_fuel_type"])), "breakdown_data": json.dumps(breakdown_chart_data(company, filters["start"], filters["end"], truck_ids, driver_ids, contract_ids, filters["city"], filters["state"], filters["selected_fuel_type"])), "operating_trucks": fleet_health_trucks.filter(status=Truck.OPERATING).count(), "maintenance_trucks": fleet_health_trucks.filter(status=Truck.MAINTENANCE).count(), "inactive_trucks": fleet_health_trucks.filter(status=Truck.INACTIVE).count(), "fleet_total": fleet_health_trucks.count(), "open_trips": Trip.objects.filter(company=company, status=Trip.IN_PROGRESS).count(), "alert_maintenance": Maintenance.objects.filter(company=company, next_date__lt=timezone.localdate(), status=Maintenance.DONE).count(), "high_cost_maintenance": Maintenance.objects.filter(company=company, date__range=(filters["start"], filters["end"]), amount__gte=5000).count(), "repeated_maintenance": repeated_maintenance, "recent_trips": Trip.objects.filter(company=company).select_related("truck", "driver", "contract")[:8]}
    return render(request, "fleet/dashboard.html", context)


@manager_required
def operation_dashboard(request):
    company = current_company(request.user)
    filters = operational_filter_context(request, company)
    trips = filtered_trips(company, filters)
    completed = trips.filter(status=Trip.FINISHED)
    distance = completed.aggregate(total=Sum("distance_km"))["total"] or Decimal("0")
    total_hours = sum((trip.duration.total_seconds() for trip in completed if trip.duration), 0) / 3600
    active = Trip.objects.filter(company=company, status=Trip.IN_PROGRESS)
    if filters["selected_truck"]:
        active = active.filter(truck_id=filters["selected_truck"])
    if filters["selected_driver"]:
        active = active.filter(driver_id=filters["selected_driver"])
    completed_with_deadline = completed.exclude(planned_end_at__isnull=True)
    on_time = completed_with_deadline.filter(ended_at__lte=F("planned_end_at")).count()
    delayed_active = active.exclude(planned_end_at__isnull=True).filter(planned_end_at__lt=timezone.now()).count()
    checklists = VehicleChecklist.objects.filter(company=company, checked_at__date__range=(filters["start"], filters["end"]))
    if filters["selected_truck"]:
        checklists = checklists.filter(truck_id=filters["selected_truck"])
    checklist_issues = sum(1 for item in checklists if item.has_issue)
    occurrences = Occurrence.objects.filter(company=company, status=Occurrence.OPEN)
    if filters["selected_truck"]:
        occurrences = occurrences.filter(truck_id=filters["selected_truck"])
    overdue_maintenance = Maintenance.objects.filter(company=company, status=Maintenance.DONE, next_date__lt=timezone.localdate())
    if filters["selected_truck"]:
        overdue_maintenance = overdue_maintenance.filter(truck_id=filters["selected_truck"])
    context = {
        **filters,
        "metrics": {
            "active": active.count(), "completed": completed.count(), "planned": trips.filter(status=Trip.PLANNED).count(),
            "distance": distance, "hours": total_hours, "average_duration": total_hours / completed.count() if completed.exists() else 0,
            "checklist_issues": checklist_issues, "occurrences": occurrences.count(), "maintenance": overdue_maintenance.count(),
            "on_time": on_time, "deadline_count": completed_with_deadline.count(), "on_time_percent": on_time * 100 / completed_with_deadline.count() if completed_with_deadline.exists() else 0, "delayed_active": delayed_active,
        },
        "active_trips": active.select_related("truck", "driver", "contract")[:6],
        "recent_trips": trips.order_by("-started_at", "-created_at")[:10],
        "chart_data": json.dumps(operational_chart_data(trips, filters["start"], filters["end"])),
    }
    return render(request, "fleet/operation_dashboard.html", context)


@driver_required
def driver_dashboard(request):
    company = current_company(request.user)
    driver = get_object_or_404(Driver, company=company, user=request.user)
    active_trip = Trip.objects.filter(company=company, driver=driver, status=Trip.IN_PROGRESS).select_related("truck", "contract").first()
    last_fuelings = Fueling.objects.filter(company=company, driver=driver).select_related("truck")[:5]
    total_km = Trip.objects.filter(company=company, driver=driver, status=Trip.FINISHED).aggregate(total=Sum("distance_km"))["total"] or Decimal("0")
    current = calculate_driver_remuneration(driver, timezone.localdate())
    planned_trips = Trip.objects.filter(company=company, driver=driver, status=Trip.PLANNED).select_related("truck", "contract")[:4]
    return render(request, "fleet/driver_dashboard.html", {"company": company, "driver": driver, "active_trip": active_trip, "planned_trips": planned_trips, "last_fuelings": last_fuelings, "total_km": total_km, "remuneration": current})


def _list_context(title, objects, create_url, **extra):
    return {"title": title, "objects": objects, "create_url": create_url, **extra}


@manager_required
def truck_list(request):
    company = current_company(request.user)
    queryset = Truck.objects.filter(company=company)
    filter_value = request.GET.get("status", "")
    financial = request.GET.get("financial", "")
    if filter_value:
        queryset = queryset.filter(status=filter_value)
    if financial:
        queryset = queryset.filter(financial_status=financial)
    return render(request, "fleet/list.html", _list_context("Caminhões", queryset, "truck_create", active_filter=filter_value, filters=[("status", "Status", Truck.STATUS_CHOICES), ("financial", "Situação financeira", Truck.FINANCIAL_CHOICES)], columns=[("identification", "Identificação"), ("simulated_plate", "Placa"), ("model", "Modelo"), ("get_status_display", "Status"), ("get_financial_status_display", "Financeiro"), ("current_odometer", "Km")], edit_url="truck_update"))


@manager_required
def truck_create(request):
    company = current_company(request.user)
    form = TruckForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit(request.user, obj, AuditLog.CREATE)
        messages.success(request, "Caminhão cadastrado com sucesso.")
        return redirect("truck_list")
    return render(request, "fleet/form.html", {"title": "Novo caminhão", "form": form, "back_url": "truck_list"})


@manager_required
def truck_update(request, pk):
    company = current_company(request.user)
    obj = get_object_or_404(Truck, company=company, pk=pk)
    before = snapshot(obj)
    form = TruckForm(request.POST or None, instance=obj, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit(request.user, obj, AuditLog.UPDATE, before=before)
        messages.success(request, "Caminhão atualizado.")
        return redirect("truck_list")
    return render(request, "fleet/form.html", {"title": f"Editar {obj.identification}", "form": form, "back_url": "truck_list"})


@manager_required
def financing_list(request):
    company = current_company(request.user)
    queryset = company.financing_set.select_related("truck").all()
    return render(request, "fleet/list.html", _list_context("Financiamentos", queryset, "financing_create", columns=[("truck", "Caminhão"), ("monthly_payment", "Parcela mensal"), ("financial_institution", "Instituição"), ("installments_paid", "Pagas"), ("installments", "Total"), ("approximate_balance", "Saldo")], edit_url="financing_update"))


@manager_required
def financing_create(request):
    company = current_company(request.user)
    form = FinancingForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Financiamento registrado."); return redirect("financing_list")
    return render(request, "fleet/form.html", {"title": "Novo financiamento", "form": form, "back_url": "financing_list", "helper": "Associe o financiamento somente a caminhões marcados como financiados."})


@manager_required
def financing_update(request, pk):
    company = current_company(request.user); obj = get_object_or_404(company.financing_set.select_related("truck"), pk=pk); before = snapshot(obj)
    form = FinancingForm(request.POST or None, instance=obj, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.UPDATE, before); messages.success(request, "Financiamento atualizado."); return redirect("financing_list")
    return render(request, "fleet/form.html", {"title": f"Editar financiamento · {obj.truck.identification}", "form": form, "back_url": "financing_list"})


@manager_required
def driver_list(request):
    company = current_company(request.user)
    queryset = Driver.objects.filter(company=company).select_related("user")
    return render(request, "fleet/list.html", _list_context("Motoristas", queryset, "driver_create", columns=[("name", "Nome"), ("user", "Usuário"), ("get_status_display", "Status"), ("monthly_fixed", "Fixo mensal"), ("phone", "Telefone")], edit_url="driver_update"))


@manager_required
def driver_create(request):
    company = current_company(request.user)
    form = DriverForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if form.cleaned_data.get("access_username"):
                access_user = User.objects.create_user(username=form.cleaned_data["access_username"], password=form.cleaned_data["access_password"], is_active=True)
                UserProfile.objects.create(user=access_user, company=company, role=UserProfile.DRIVER)
                form.instance.user = access_user
            obj = form.save()
        audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Motorista cadastrado."); return redirect("driver_list")
    return render(request, "fleet/form.html", {"title": "Novo motorista", "form": form, "back_url": "driver_list"})


@manager_required
def driver_update(request, pk):
    company = current_company(request.user); obj = get_object_or_404(Driver, company=company, pk=pk); before = snapshot(obj)
    form = DriverForm(request.POST or None, instance=obj, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if form.cleaned_data.get("access_username"):
                access_user = User.objects.create_user(username=form.cleaned_data["access_username"], password=form.cleaned_data["access_password"], is_active=True)
                UserProfile.objects.create(user=access_user, company=company, role=UserProfile.DRIVER)
                form.instance.user = access_user
            obj = form.save()
        audit(request.user, obj, AuditLog.UPDATE, before); messages.success(request, "Motorista atualizado."); return redirect("driver_list")
    return render(request, "fleet/form.html", {"title": f"Editar {obj.name}", "form": form, "back_url": "driver_list"})


@manager_required
def contract_list(request):
    company = current_company(request.user)
    queryset = Contract.objects.filter(company=company)
    return render(request, "fleet/list.html", _list_context("Contratos", queryset, "contract_create", columns=[("code", "Código"), ("client_name", "Cliente"), ("get_status_display", "Status"), ("get_production_type_display", "Produção"), ("contracted_value", "Valor contratado")], edit_url="contract_update"))


@manager_required
def contract_create(request):
    company = current_company(request.user); form = ContractForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Contrato criado."); return redirect("contract_list")
    return render(request, "fleet/form.html", {"title": "Novo contrato", "form": form, "back_url": "contract_list"})


@manager_required
def contract_update(request, pk):
    company = current_company(request.user); obj = get_object_or_404(Contract, company=company, pk=pk); before = snapshot(obj); form = ContractForm(request.POST or None, instance=obj, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.UPDATE, before); messages.success(request, "Contrato atualizado."); return redirect("contract_list")
    return render(request, "fleet/form.html", {"title": f"Editar {obj.code}", "form": form, "back_url": "contract_list"})


@login_required
def trip_list(request):
    company = current_company(request.user)
    queryset = Trip.objects.filter(company=company).select_related("truck", "driver", "contract")
    profile = profile_for(request.user)
    if profile and profile.role == UserProfile.DRIVER:
        queryset = queryset.filter(driver__user=request.user)
    create_url = "trip_start" if profile and profile.role == UserProfile.DRIVER else "trip_plan_create"
    return render(request, "fleet/list.html", _list_context("Trechos", queryset, create_url, columns=[("origin", "Origem"), ("destination", "Destino"), ("truck", "Caminhão"), ("driver", "Motorista"), ("get_status_display", "Status"), ("distance_km", "Km")], detail_url="trip_detail"))


@manager_required
def trip_plan_create(request):
    company = current_company(request.user)
    form = TripPlanForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        trip = form.save(commit=False)
        trip.company = company
        trip.status = Trip.PLANNED
        trip.created_by = request.user
        trip.updated_by = request.user
        trip.full_clean()
        trip.save()
        audit(request.user, trip, AuditLog.CREATE)
        messages.success(request, "Trecho planejado e disponibilizado ao motorista.")
        return redirect("trip_list")
    return render(request, "fleet/form.html", {"title": "Planejar trecho", "form": form, "back_url": "trip_list", "helper": "O motorista confirmará a quilometragem real ao iniciar a viagem."})


@driver_required
def trip_start(request):
    company = current_company(request.user); driver = get_object_or_404(Driver, company=company, user=request.user)
    form = TripStartForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        trip = form.save(commit=False); trip.company = company; trip.driver = driver; trip.created_by = request.user; trip.updated_by = request.user
        try:
            with transaction.atomic():
                trip.truck = Truck.objects.select_for_update().get(company=company, pk=trip.truck_id)
                trip.driver = Driver.objects.select_for_update().get(company=company, pk=driver.pk)
                trip.full_clean(); trip.start(); trip.save(); audit(request.user, trip, AuditLog.CREATE)
            messages.success(request, "Trecho iniciado. Boa viagem!"); return redirect("driver_dashboard")
        except Exception as exc:
            form.add_error(None, str(exc))
    return render(request, "fleet/form.html", {"title": "Iniciar trecho", "form": form, "back_url": "driver_dashboard", "helper": "A data e hora serão registradas automaticamente ao iniciar."})


@driver_required
def trip_start_planned(request, pk):
    company = current_company(request.user)
    driver = get_object_or_404(Driver, company=company, user=request.user)
    trip = get_object_or_404(Trip.objects.select_related("truck", "contract"), company=company, driver=driver, pk=pk, status=Trip.PLANNED)
    form = TripStartPlannedForm(request.POST or None, initial={"start_odometer": trip.truck.current_odometer, "notes": trip.notes})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                trip = Trip.objects.select_for_update().select_related("truck").get(company=company, driver=driver, pk=pk, status=Trip.PLANNED)
                trip.truck = Truck.objects.select_for_update().get(company=company, pk=trip.truck_id)
                before = snapshot(trip)
                trip.start_odometer = form.cleaned_data["start_odometer"]
                trip.notes = form.cleaned_data["notes"] or trip.notes
                trip.updated_by = request.user
                trip.full_clean()
                trip.start()
                trip.save()
                audit(request.user, trip, AuditLog.UPDATE, before)
            messages.success(request, "Trecho planejado iniciado. Boa viagem!")
            return redirect("driver_dashboard")
        except Exception as exc:
            form.add_error(None, str(exc))
    return render(request, "fleet/form.html", {"title": "Iniciar trecho planejado", "form": form, "back_url": "driver_dashboard", "helper": f"Rota: {trip.origin} → {trip.destination}. Confirme a quilometragem atual antes de sair."})


@login_required
def trip_detail(request, pk):
    company = current_company(request.user); trip = get_object_or_404(Trip.objects.select_related("truck", "driver", "contract"), company=company, pk=pk)
    profile = profile_for(request.user)
    if profile and profile.role == UserProfile.DRIVER and trip.driver.user_id != request.user.id:
        return HttpResponseForbidden("Você só pode consultar seus próprios trechos.")
    return render(request, "fleet/trip_detail.html", {"trip": trip, "stops": trip.stops.all(), "can_reopen": request.user.is_superuser or (profile and profile.role == UserProfile.MANAGER)})


@driver_required
def trip_finish(request, pk):
    company = current_company(request.user); driver = get_object_or_404(Driver, company=company, user=request.user); trip = get_object_or_404(Trip, company=company, driver=driver, pk=pk, status=Trip.IN_PROGRESS)
    form = TripFinishForm(request.POST or None, request.FILES or None, initial={"end_odometer": trip.truck.current_odometer})
    if request.method == "POST" and form.is_valid():
        before = snapshot(trip)
        try:
            with transaction.atomic():
                trip = Trip.objects.select_for_update().select_related("truck").get(company=company, driver=driver, pk=pk, status=Trip.IN_PROGRESS)
                trip.truck = Truck.objects.select_for_update().get(company=company, pk=trip.truck_id)
                trip.finish(form.cleaned_data["end_odometer"], form.cleaned_data["notes"])
                if form.cleaned_data.get("delivery_proof"):
                    trip.delivery_proof = form.cleaned_data["delivery_proof"]
                trip.updated_by = request.user; trip.save(); audit(request.user, trip, AuditLog.UPDATE, before)
            messages.success(request, "Trecho finalizado e bloqueado para edição."); return redirect("driver_dashboard")
        except Exception as exc:
            form.add_error("end_odometer", str(exc))
    return render(request, "fleet/form.html", {"title": "Finalizar trecho", "form": form, "back_url": "driver_dashboard", "helper": f"Trecho: {trip.origin} → {trip.destination}"})


@driver_required
def stop_create(request, pk):
    company = current_company(request.user); driver = get_object_or_404(Driver, company=company, user=request.user); trip = get_object_or_404(Trip, company=company, driver=driver, pk=pk, status=Trip.IN_PROGRESS)
    form = StopForm(request.POST or None, trip=trip)
    if request.method == "POST" and form.is_valid():
        stop = form.save(commit=False); stop.trip = trip; stop.full_clean(); stop.save(); messages.success(request, "Parada adicionada ao trecho."); return redirect("trip_detail", pk=trip.pk)
    return render(request, "fleet/form.html", {"title": "Adicionar parada", "form": form, "back_url": "trip_detail", "back_kwargs": {"pk": trip.pk}})


@login_required
def fueling_list(request):
    company = current_company(request.user); queryset = Fueling.objects.filter(company=company).select_related("truck", "driver", "trip")
    profile = profile_for(request.user)
    if profile and profile.role == UserProfile.DRIVER:
        queryset = queryset.filter(driver__user=request.user)
        return render(request, "fleet/list.html", _list_context("Abastecimentos", queryset, "fueling_create", columns=[("truck", "Caminhão"), ("fueled_at", "Data"), ("city", "Cidade"), ("liters", "Litros"), ("total_amount", "Valor"), ("price_per_liter", "R$/L"), ("km_per_liter", "Km/L")]))
    filters = operational_filter_context(request, company, default_days=90)
    queryset = queryset.filter(fueled_at__date__range=(filters["start"], filters["end"]))
    for field in ("truck", "driver", "fuel_type"):
        if filters[f"selected_{field}"]:
            lookup = f"{field}_id" if field in ("truck", "driver") else field
            queryset = queryset.filter(**{lookup: filters[f"selected_{field}"]})
    if filters["selected_city"]:
        queryset = queryset.filter(city__icontains=filters["selected_city"])
    if filters["selected_state"]:
        queryset = queryset.filter(state__iexact=filters["selected_state"])
    if filters["selected_tank_full"] in ("1", "0"):
        queryset = queryset.filter(tank_full=filters["selected_tank_full"] == "1")
    totals = queryset.aggregate(amount=Sum("total_amount"), liters=Sum("liters"), average_km_l=Avg("km_per_liter"), full_tanks=Count("id", filter=Q(tank_full=True)))
    total_amount, total_liters = totals["amount"] or Decimal("0"), totals["liters"] or Decimal("0")
    context = {
        **filters,
        "fuelings": queryset.order_by("-fueled_at"),
        "metrics": {"amount": total_amount, "liters": total_liters, "average_price": total_amount / total_liters if total_liters else Decimal("0"), "average_km_l": totals["average_km_l"] or Decimal("0"), "full_tanks": totals["full_tanks"] or 0},
        "chart_data": json.dumps(fuel_chart_data(queryset, filters["start"], filters["end"])),
    }
    return render(request, "fleet/fueling_management.html", context)


@driver_required
def fueling_create(request):
    company = current_company(request.user); driver = get_object_or_404(Driver, company=company, user=request.user)
    active_trip = Trip.objects.filter(company=company, driver=driver, status=Trip.IN_PROGRESS).select_related("truck").first()
    initial = {"fueled_at": timezone.localtime().replace(second=0, microsecond=0)}
    if active_trip:
        initial.update({"trip": active_trip.pk, "truck": active_trip.truck_id, "odometer": active_trip.truck.current_odometer})
    form = FuelingForm(request.POST or None, request.FILES or None, company=company, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        fueling = form.save(commit=False); fueling.company = company; fueling.driver = driver; fueling.created_by = request.user; fueling.updated_by = request.user
        try:
            with transaction.atomic():
                fueling.truck = Truck.objects.select_for_update().get(company=company, pk=fueling.truck_id)
                fueling.full_clean(); fueling.save(); audit(request.user, fueling, AuditLog.CREATE)
            messages.success(request, "Abastecimento registrado."); return redirect("driver_dashboard")
        except Exception as exc:
            form.add_error(None, str(exc))
    return render(request, "fleet/form.html", {"title": "Registrar abastecimento", "form": form, "back_url": "driver_dashboard", "helper": "O preço por litro é calculado automaticamente. Km/L só aparece com tanque completo e histórico válido."})


@login_required
def checklist_list(request):
    company = current_company(request.user)
    queryset = VehicleChecklist.objects.filter(company=company).select_related("truck", "driver", "trip")
    profile = profile_for(request.user)
    if profile and profile.role == UserProfile.DRIVER:
        queryset = queryset.filter(driver__user=request.user)
    create_url = "checklist_create" if profile and profile.role == UserProfile.DRIVER else None
    return render(request, "fleet/list.html", _list_context("Checklists do veículo", queryset, create_url, columns=[("checked_at", "Data"), ("truck", "Caminhão"), ("driver", "Motorista"), ("status_label", "Situação")]))


@driver_required
def checklist_create(request):
    company = current_company(request.user)
    driver = get_object_or_404(Driver, company=company, user=request.user)
    active_trip = Trip.objects.filter(company=company, driver=driver, status=Trip.IN_PROGRESS).first()
    initial = {"truck": active_trip.truck_id, "trip": active_trip.pk} if active_trip else None
    form = VehicleChecklistForm(request.POST or None, company=company, user=request.user, driver=driver, initial=initial)
    if request.method == "POST" and form.is_valid():
        checklist = form.save(commit=False)
        checklist.company = company
        checklist.driver = driver
        checklist.created_by = request.user
        checklist.updated_by = request.user
        checklist.full_clean()
        checklist.save()
        audit(request.user, checklist, AuditLog.CREATE)
        messages.success(request, "Checklist registrado." if not checklist.has_issue else "Checklist registrado com pendências para acompanhamento.")
        return redirect("driver_dashboard")
    return render(request, "fleet/form.html", {"title": "Checklist do veículo", "form": form, "back_url": "driver_dashboard", "helper": "Desmarque apenas os itens com problema e descreva a situação nas observações."})


@driver_required
def occurrence_create(request):
    company = current_company(request.user)
    driver = get_object_or_404(Driver, company=company, user=request.user)
    form = OccurrenceForm(request.POST or None, company=company, user=request.user, driver=driver)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.company = company
        obj.driver = driver
        obj.created_by = request.user
        obj.updated_by = request.user
        obj.full_clean()
        obj.save()
        audit(request.user, obj, AuditLog.CREATE)
        messages.success(request, "Ocorrência registrada. O gestor poderá acompanhá-la.")
        return redirect("driver_dashboard")
    return render(request, "fleet/form.html", {"title": "Informar problema", "form": form, "back_url": "driver_dashboard", "helper": "Descreva o problema com clareza para agilizar o atendimento."})


@manager_required
def maintenance_list(request):
    company = current_company(request.user)
    filters = operational_filter_context(request, company, default_days=90)
    queryset = Maintenance.objects.filter(company=company, date__range=(filters["start"], filters["end"])).select_related("truck")
    if filters["selected_truck"]:
        queryset = queryset.filter(truck_id=filters["selected_truck"])
    selected_type, selected_status = request.GET.get("type", ""), request.GET.get("status", "")
    if selected_type in dict(Maintenance.TYPE_CHOICES):
        queryset = queryset.filter(maintenance_type=selected_type)
    if selected_status in dict(Maintenance.STATUS_CHOICES):
        queryset = queryset.filter(status=selected_status)
    plans = MaintenancePlan.objects.filter(company=company, active=True).select_related("truck")
    if filters["selected_truck"]:
        plans = plans.filter(truck_id=filters["selected_truck"])
    due_plans = [plan for plan in plans if plan.due_status == "Vencido"]
    total_cost = queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_downtime = queryset.aggregate(total=Sum("downtime_days"))["total"] or 0
    by_type = list(queryset.values("maintenance_type").annotate(value=Sum("amount")).order_by("-value"))
    by_truck = list(queryset.values("truck_id", "truck__identification").annotate(value=Sum("amount")).order_by("-value"))
    context = {**filters, "maintenances": queryset.order_by("-date"), "plans": plans[:8], "due_plans": due_plans[:8], "selected_type": selected_type, "selected_status": selected_status, "maintenance_types": Maintenance.TYPE_CHOICES, "maintenance_statuses": Maintenance.STATUS_CHOICES, "metrics": {"cost": total_cost, "downtime": total_downtime, "open": queryset.filter(status=Maintenance.OPEN).count(), "due": len(due_plans)}, "chart_data": json.dumps({"types": {"labels": [dict(Maintenance.TYPE_CHOICES).get(row["maintenance_type"]) for row in by_type], "keys": [row["maintenance_type"] for row in by_type], "values": [float(row["value"] or 0) for row in by_type]}, "trucks": {"labels": [row["truck__identification"] for row in by_truck], "ids": [row["truck_id"] for row in by_truck], "values": [float(row["value"] or 0) for row in by_truck]}})}
    return render(request, "fleet/maintenance_management.html", context)


@manager_required
def maintenance_create(request):
    company = current_company(request.user); form = MaintenanceForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Manutenção registrada."); return redirect("maintenance_list")
    return render(request, "fleet/form.html", {"title": "Nova manutenção", "form": form, "back_url": "maintenance_list"})


@manager_required
def maintenance_plan_create(request):
    company = current_company(request.user); form = MaintenancePlanForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Plano preventivo criado."); return redirect("maintenance_list")
    return render(request, "fleet/form.html", {"title": "Novo plano preventivo", "form": form, "back_url": "maintenance_list", "helper": "Defina a próxima revisão por data, quilometragem ou ambos."})


@manager_required
def cashflow_view(request):
    company = current_company(request.user)
    filters = operational_filter_context(request, company, default_days=90)
    queryset = CashEntry.objects.filter(company=company, due_date__range=(filters["start"], filters["end"])).select_related("truck", "contract")
    selected_type, selected_status = request.GET.get("entry_type", ""), request.GET.get("status", "")
    if selected_type in dict(CashEntry.ENTRY_TYPE_CHOICES): queryset = queryset.filter(entry_type=selected_type)
    if selected_status in dict(CashEntry.STATUS_CHOICES): queryset = queryset.filter(status=selected_status)
    if filters["selected_truck"]: queryset = queryset.filter(truck_id=filters["selected_truck"])
    receivable = queryset.filter(entry_type=CashEntry.RECEIVABLE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    payable = queryset.filter(entry_type=CashEntry.PAYABLE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    pending = list(queryset.exclude(status__in=(CashEntry.PAID, CashEntry.CANCELLED)))
    overdue = [entry for entry in pending if entry.is_overdue]
    categories = list(queryset.values("category", "entry_type").annotate(value=Sum("amount")).order_by("-value")[:8])
    context = {**filters, "entries": queryset.order_by("due_date"), "selected_type": selected_type, "selected_status": selected_status, "entry_types": CashEntry.ENTRY_TYPE_CHOICES, "cash_statuses": CashEntry.STATUS_CHOICES, "metrics": {"receivable": receivable, "payable": payable, "projected": receivable - payable, "pending": sum((entry.amount for entry in pending), Decimal("0")), "overdue": sum((entry.amount for entry in overdue), Decimal("0"))}, "chart_data": json.dumps({"labels": [row["category"] for row in categories], "keys": [row["entry_type"] for row in categories], "values": [float(row["value"] or 0) for row in categories]})}
    return render(request, "fleet/cashflow.html", context)


@manager_required
def cash_entry_create(request):
    company = current_company(request.user); form = CashEntryForm(request.POST or None, request.FILES or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Conta financeira registrada."); return redirect("cashflow_view")
    return render(request, "fleet/form.html", {"title": "Nova conta financeira", "form": form, "back_url": "cashflow_view"})


@manager_required
def cash_entry_transition(request, pk, action):
    company = current_company(request.user); entry = get_object_or_404(CashEntry, company=company, pk=pk)
    if request.method != "POST":
        return HttpResponseForbidden("Ação inválida.")
    before = snapshot(entry)
    if action == "approve" and entry.status == CashEntry.PENDING:
        entry.status = CashEntry.APPROVED
    elif action == "pay" and entry.status in (CashEntry.PENDING, CashEntry.APPROVED):
        entry.status, entry.paid_at = CashEntry.PAID, timezone.localdate()
    else:
        messages.error(request, "Esta transição não está disponível para a conta.")
        return redirect("cashflow_view")
    entry.updated_by = request.user; entry.save(); audit(request.user, entry, AuditLog.UPDATE, before, action)
    messages.success(request, "Conta aprovada." if action == "approve" else "Conta liquidada.")
    return redirect("cashflow_view")


@manager_required
def tire_create(request):
    company = current_company(request.user); form = TireExpenseForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Despesa com pneus registrada."); return redirect("maintenance_list")
    return render(request, "fleet/form.html", {"title": "Registrar despesa com pneus", "form": form, "back_url": "maintenance_list"})


@manager_required
def production_list(request):
    company = current_company(request.user)
    start, end = filter_period(request)
    queryset = Production.objects.filter(company=company, competence__range=(start, end)).select_related("contract", "truck", "driver")
    for key in ("contract", "truck", "driver", "status"):
        if request.GET.get(key):
            queryset = queryset.filter(**{f"{key}_id" if key != "status" else key: request.GET[key]})
    status_labels = dict(Production.STATUS_CHOICES)
    monthly_rows = list(queryset.values("competence__year", "competence__month").annotate(total=Sum("realized_value")).order_by("competence__year", "competence__month"))
    status_rows = list(queryset.values("status").annotate(total=Sum("realized_value"), count=Count("id")).order_by("status"))
    contract_rows = list(queryset.values("contract_id", "contract__code").annotate(total=Sum("realized_value")).order_by("-total"))
    total = queryset.aggregate(total=Sum("realized_value"))["total"] or Decimal("0")
    approved = queryset.filter(status=Production.APPROVED).aggregate(total=Sum("realized_value"))["total"] or Decimal("0")
    context = _list_context(
        "Produção financeira", queryset, "production_create", start=start, end=end,
        selected_contract=request.GET.get("contract", ""), selected_truck=request.GET.get("truck", ""), selected_driver=request.GET.get("driver", ""), selected_status=request.GET.get("status", ""),
        production_contracts=Contract.objects.filter(company=company), production_trucks=Truck.objects.filter(company=company), production_drivers=Driver.objects.filter(company=company), production_statuses=Production.STATUS_CHOICES,
        summary={"total": total, "count": queryset.count(), "approved": approved, "active_contracts": queryset.values("contract_id").distinct().count()},
        production_chart=json.dumps({"labels": [date(row["competence__year"], row["competence__month"], 1).strftime("%b/%y") for row in monthly_rows], "values": [float(row["total"] or 0) for row in monthly_rows], "starts": [date(row["competence__year"], row["competence__month"], 1).isoformat() for row in monthly_rows], "ends": [date(row["competence__year"], row["competence__month"], monthrange(row["competence__year"], row["competence__month"])[1]).isoformat() for row in monthly_rows]}),
        production_status_chart=json.dumps({"labels": [status_labels[row["status"]] for row in status_rows], "keys": [row["status"] for row in status_rows], "values": [float(row["total"] or 0) for row in status_rows], "counts": [row["count"] for row in status_rows]}),
        production_contract_chart=json.dumps({"labels": [row["contract__code"] for row in contract_rows], "ids": [row["contract_id"] for row in contract_rows], "values": [float(row["total"] or 0) for row in contract_rows]}),
    )
    return render(request, "fleet/production.html", context)


@manager_required
def production_create(request):
    company = current_company(request.user); form = ProductionForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Produção financeira registrada."); return redirect("production_list")
    return render(request, "fleet/form.html", {"title": "Registrar produção", "form": form, "back_url": "production_list", "helper": "A comissão usa o valor realizado informado aqui."})


@manager_required
def rule_list(request):
    company = current_company(request.user); queryset = RemunerationRule.objects.filter(company=company).select_related("driver", "contract")
    return render(request, "fleet/list.html", _list_context("Regras de remuneração", queryset, "rule_create", columns=[("driver", "Motorista"), ("contract", "Contrato"), ("effective_from", "Vigência"), ("priority", "Prioridade"), ("commission_percent", "Comissão"), ("get_bonus_type_display", "Bônus"), ("active", "Ativa")]))


@manager_required
def rule_create(request):
    company = current_company(request.user); form = RemunerationRuleForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Regra criada. Regras utilizadas historicamente devem ser desativadas, não apagadas."); return redirect("rule_list")
    return render(request, "fleet/form.html", {"title": "Nova regra de remuneração", "form": form, "back_url": "rule_list"})


@manager_required
def fixed_cost_list(request):
    company = current_company(request.user)
    start, end = filter_period(request)
    queryset = FixedCost.objects.filter(company=company, valid_from__lte=end).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start)).select_related("truck")
    selected_category = request.GET.get("category", "")
    selected_truck = request.GET.get("truck", "")
    selected_active = request.GET.get("active", "")
    if selected_category:
        queryset = queryset.filter(category=selected_category)
    if selected_truck:
        queryset = queryset.filter(truck_id=selected_truck)
    if selected_active:
        queryset = queryset.filter(active=selected_active == "1")
    category_labels = dict(FixedCost.CATEGORY_CHOICES)
    category_rows = list(queryset.values("category").annotate(total=Sum("monthly_amount")).order_by("category"))
    truck_rows = list(queryset.filter(truck__isnull=False).values("truck_id", "truck__identification").annotate(total=Sum("monthly_amount")).order_by("-total"))
    monthly_total = queryset.filter(active=True).aggregate(total=Sum("monthly_amount"))["total"] or Decimal("0")
    context = _list_context(
        "Custos fixos", queryset, "fixed_cost_create", start=start, end=end, trucks=Truck.objects.filter(company=company), categories=FixedCost.CATEGORY_CHOICES,
        selected_category=selected_category, selected_truck=selected_truck, selected_active=selected_active,
        summary={"monthly": monthly_total, "annual": monthly_total * Decimal("12"), "active_count": queryset.filter(active=True).count(), "count": queryset.count()},
        fixed_category_chart=json.dumps({"labels": [category_labels[row["category"]] for row in category_rows], "keys": [row["category"] for row in category_rows], "values": [float(row["total"] or 0) for row in category_rows]}),
        fixed_truck_chart=json.dumps({"labels": [row["truck__identification"] for row in truck_rows], "ids": [row["truck_id"] for row in truck_rows], "values": [float(row["total"] or 0) for row in truck_rows]}),
    )
    return render(request, "fleet/fixed_costs.html", context)


@manager_required
def fixed_cost_create(request):
    company = current_company(request.user); form = FixedCostForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); audit(request.user, obj, AuditLog.CREATE); messages.success(request, "Custo fixo cadastrado."); return redirect("fixed_cost_list")
    return render(request, "fleet/form.html", {"title": "Novo custo fixo", "form": form, "back_url": "fixed_cost_list"})


@manager_required
def remuneration_view(request):
    company = current_company(request.user)
    competence = parse_date(request.GET.get("competence") + "-01" if request.GET.get("competence") and len(request.GET.get("competence")) == 7 else request.GET.get("competence"), timezone.localdate()).replace(day=1)
    selected_driver = request.GET.get("driver", "")
    drivers = Driver.objects.filter(company=company, status=Driver.ACTIVE)
    if selected_driver:
        drivers = drivers.filter(pk=selected_driver)
    rows = []
    for driver in drivers:
        calculation = calculate_driver_remuneration(driver, competence); remuneration, _ = Remuneration.objects.get_or_create(company=company, driver=driver, competence=competence.replace(day=1), defaults={**{key: calculation[key] for key in ("fixed_amount", "commission_base_value", "commission_percent", "commission_amount", "km_bonus", "trips_bonus", "other_bonus", "total_amount", "calculation_notes")}, "created_by": request.user, "updated_by": request.user})
        rows.append((driver, calculation, remuneration))
    totals = {key: sum((row[1][key] for row in rows), Decimal("0")) for key in ("fixed_amount", "commission_amount", "km_bonus", "trips_bonus", "other_bonus", "total_amount")}
    history = []
    for offset in range(-5, 1):
        month = shift_month(competence, offset)
        monthly = [calculate_driver_remuneration(driver, month) for driver in drivers]
        history.append({"label": month.strftime("%b/%y"), "competence": month.strftime("%Y-%m"), "total": float(sum((item["total_amount"] for item in monthly), Decimal("0"))), "fixed": float(sum((item["fixed_amount"] for item in monthly), Decimal("0"))), "commission": float(sum((item["commission_amount"] for item in monthly), Decimal("0"))), "bonus": float(sum((item["km_bonus"] + item["trips_bonus"] + item["other_bonus"] for item in monthly), Decimal("0")))})
    return render(request, "fleet/remuneration.html", {"company": company, "competence": competence.replace(day=1), "rows": rows, "drivers": Driver.objects.filter(company=company, status=Driver.ACTIVE), "selected_driver": selected_driver, "summary": totals, "remuneration_driver_chart": json.dumps({"labels": [row[0].name for row in rows], "ids": [row[0].pk for row in rows], "fixed": [float(row[1]["fixed_amount"]) for row in rows], "commission": [float(row[1]["commission_amount"]) for row in rows], "bonus": [float(row[1]["km_bonus"] + row[1]["trips_bonus"] + row[1]["other_bonus"]) for row in rows], "total": [float(row[1]["total_amount"]) for row in rows]}), "remuneration_history_chart": json.dumps(history)})


@driver_required
def driver_remuneration_view(request):
    company = current_company(request.user)
    driver = get_object_or_404(Driver, company=company, user=request.user)
    raw_competence = request.GET.get("competence")
    competence = parse_date(raw_competence + "-01" if raw_competence and len(raw_competence) == 7 else raw_competence, timezone.localdate()).replace(day=1)
    calculation = calculate_driver_remuneration(driver, competence)
    remuneration, _ = Remuneration.objects.get_or_create(company=company, driver=driver, competence=competence, defaults={**{key: calculation[key] for key in ("fixed_amount", "commission_base_value", "commission_percent", "commission_amount", "km_bonus", "trips_bonus", "other_bonus", "total_amount", "calculation_notes")}, "created_by": request.user, "updated_by": request.user})
    return render(request, "fleet/remuneration_driver.html", {"company": company, "driver": driver, "competence": competence, "calculation": calculation, "remuneration": remuneration})


@manager_required
def reopen_trip(request, pk):
    company = current_company(request.user); trip = get_object_or_404(Trip, company=company, pk=pk, status=Trip.FINISHED)
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Informe o motivo da reabertura.")
        else:
            before = snapshot(trip); trip.status = Trip.REOPENED; trip.updated_by = request.user; trip.save(update_fields=["status", "updated_by", "updated_at"]); audit(request.user, trip, AuditLog.REOPEN, before, reason); messages.success(request, "Trecho reaberto para correção."); return redirect("trip_detail", pk=pk)
    return render(request, "fleet/reopen.html", {"trip": trip})


@manager_required
def trip_update(request, pk):
    company = current_company(request.user); trip = get_object_or_404(Trip, company=company, pk=pk, status=Trip.REOPENED)
    form = TripFinishForm(request.POST or None, initial={"end_odometer": trip.end_odometer, "notes": trip.notes})
    if request.method == "POST" and form.is_valid():
        before = snapshot(trip)
        try:
            end = form.cleaned_data["end_odometer"]
            if end < trip.start_odometer: raise ValueError("A quilometragem final não pode ser menor que a inicial.")
            trip.end_odometer = end; trip.distance_km = end - trip.start_odometer; trip.notes = form.cleaned_data["notes"]; trip.status = Trip.FINISHED; trip.updated_by = request.user; trip.save(); audit(request.user, trip, AuditLog.UPDATE, before, "Correção após reabertura"); messages.success(request, "Correção salva e trecho bloqueado novamente."); return redirect("trip_detail", pk=pk)
        except Exception as exc: form.add_error("end_odometer", str(exc))
    return render(request, "fleet/form.html", {"title": "Corrigir trecho", "form": form, "back_url": "trip_detail", "back_kwargs": {"pk": pk}})


@manager_required
def report_view(request, report_name):
    company = current_company(request.user); start, end = filter_period(request); base = {"company": company, "start": start, "end": end, "report_name": report_name}
    if report_name == "custos":
        selected_truck = request.GET.get("truck", "")
        cost_components = (("fuel", "Combustível"), ("maintenance", "Manutenção"), ("tires", "Pneus"), ("financing", "Financiamento"), ("fixed", "Custos fixos"), ("remuneration", "Remuneração"))
        selected_component = request.GET.get("component", "")
        if selected_component not in dict(cost_components):
            selected_component = ""
        truck_queryset = Truck.objects.filter(company=company)
        if selected_truck:
            truck_queryset = truck_queryset.filter(pk=selected_truck)
        rows = []
        for truck in truck_queryset:
            costs = truck_costs(company, start, end, truck.pk)
            distance = Trip.objects.filter(company=company, truck=truck, status=Trip.FINISHED, started_at__date__range=(start, end)).aggregate(value=Sum("distance_km"))["value"] or Decimal("0")
            total = sum(costs.values(), Decimal("0"))
            rows.append({"truck": truck, **costs, "distance": distance, "cost_per_km": total / distance if distance else Decimal("0"), "total": total})
        if selected_component:
            rows = [row for row in rows if row[selected_component] > 0]
        selected_ids = list(truck_queryset.values_list("id", flat=True)) if selected_truck else None
        metrics = dashboard_metrics(company, start, end, selected_ids)
        base.update({"title": "Custos por caminhão", "trucks": Truck.objects.filter(company=company), "selected_truck": selected_truck, "selected_component": selected_component, "selected_component_label": dict(cost_components).get(selected_component, ""), "cost_components": cost_components, "rows": rows, "summary": {"fuel": metrics["fuel"], "maintenance": metrics["maintenance"], "tires": metrics["tires"], "financing": metrics["financing"], "fixed": metrics["fixed"], "remuneration": metrics["remuneration"], "total": metrics["total_cost"], "distance": metrics["distance"], "cost_per_km": metrics["cost_per_km"]}, "cost_chart": json.dumps({"labels": [label for key, label in cost_components], "keys": [key for key, label in cost_components], "values": [float(metrics[key]) for key, label in cost_components]}), "truck_chart": json.dumps({"labels": [row["truck"].identification for row in rows], "ids": [row["truck"].pk for row in rows], "values": [float(row[selected_component] if selected_component else row["total"]) for row in rows]})})
        return render(request, "fleet/costs_report.html", base)
    elif report_name == "resultado":
        selected_truck = request.GET.get("truck", "")
        truck_queryset = Truck.objects.filter(company=company)
        if selected_truck:
            truck_queryset = truck_queryset.filter(pk=selected_truck)
        rows = []
        allocation = production_allocation(company, start, end)
        for truck in truck_queryset:
            costs = truck_costs(company, start, end, truck.pk)
            distance = Trip.objects.filter(company=company, truck=truck, status=Trip.FINISHED, started_at__date__range=(start, end)).aggregate(value=Sum("distance_km"))["value"] or Decimal("0")
            revenue = allocation.get(truck.pk, Decimal("0"))
            total = sum(costs.values(), Decimal("0"))
            result = revenue - total
            rows.append({"truck": truck, "revenue": revenue, **costs, "distance": distance, "cost": total, "cost_per_km": total / distance if distance else Decimal("0"), "result": result, "margin": (result / revenue * Decimal("100")) if revenue else Decimal("0")})
        selected_ids = list(truck_queryset.values_list("id", flat=True)) if selected_truck else None
        metrics = dashboard_metrics(company, start, end, selected_ids)
        margin = metrics["result"] / metrics["revenue"] * Decimal("100") if metrics["revenue"] else Decimal("0")
        base.update({"title": "Resultado operacional estimado", "trucks": Truck.objects.filter(company=company), "selected_truck": selected_truck, "rows": rows, "summary": {"revenue": metrics["revenue"], "cost": metrics["total_cost"], "result": metrics["result"], "distance": metrics["distance"], "cost_per_km": metrics["cost_per_km"], "margin": margin, "fuel": metrics["fuel"], "maintenance": metrics["maintenance"], "tires": metrics["tires"], "financing": metrics["financing"], "fixed": metrics["fixed"], "remuneration": metrics["remuneration"]}, "result_chart": json.dumps({"labels": [row["truck"].identification for row in rows], "ids": [row["truck"].pk for row in rows], "revenue": [float(row["revenue"]) for row in rows], "cost": [float(row["cost"]) for row in rows], "result": [float(row["result"]) for row in rows]}), "monthly_result_chart": json.dumps(monthly_chart_data(company, start, end, selected_ids))})
        return render(request, "fleet/result_report.html", base)
    elif report_name == "abastecimentos":
        base.update({"title": "Abastecimentos e consumo", "columns": [("truck", "Caminhão"), ("fueled_at", "Data"), ("city", "Cidade"), ("liters", "Litros"), ("total_amount", "Valor"), ("price_per_liter", "R$/L"), ("km_per_liter", "Km/L")], "rows": Fueling.objects.filter(company=company, fueled_at__date__range=(start, end)).select_related("truck")})
    elif report_name == "manutencoes":
        base.update({"title": "Manutenções", "columns": [("truck", "Caminhão"), ("date", "Data"), ("get_maintenance_type_display", "Tipo"), ("description", "Descrição"), ("amount", "Valor")], "rows": Maintenance.objects.filter(company=company, date__range=(start, end)).select_related("truck")})
    elif report_name == "producao":
        base.update({"title": "Produção por contrato", "columns": [("contract", "Contrato"), ("competence", "Competência"), ("realized_value", "Realizado"), ("status", "Status")], "rows": Production.objects.filter(company=company, competence__range=(start, end)).select_related("contract")})
    elif report_name == "remuneracao":
        base.update({"title": "Remuneração por motorista", "columns": [("driver", "Motorista"), ("competence", "Competência"), ("fixed_amount", "Fixo"), ("commission_amount", "Comissão"), ("km_bonus", "Bônus km"), ("trips_bonus", "Bônus viagens"), ("total_amount", "Total")], "rows": Remuneration.objects.filter(company=company, competence__range=(start, end)).select_related("driver")})
    elif report_name == "trechos":
        base.update({"title": "Trechos realizados", "columns": [("origin", "Origem"), ("destination", "Destino"), ("truck", "Caminhão"), ("driver", "Motorista"), ("started_at", "Início"), ("distance_km", "Km")], "rows": Trip.objects.filter(company=company, status=Trip.FINISHED, started_at__date__range=(start, end)).select_related("truck", "driver")})
    else:
        base.update({"title": "Resultado operacional estimado", "columns": [("truck", "Caminhão"), ("revenue", "Receita"), ("cost", "Custos"), ("result", "Resultado")], "rows": []})
        allocation = production_allocation(company, start, end)
        for truck in Truck.objects.filter(company=company):
            revenue = allocation.get(truck.pk, Decimal("0")); costs = truck_costs(company, start, end, truck.pk); cost = sum(costs.values(), Decimal("0")); base["rows"].append({"truck": truck, "revenue": revenue, "cost": cost, "result": revenue - cost})
    return render(request, "fleet/report.html", base)


@manager_required
def report_csv(request, report_name):
    response = HttpResponse(content_type="text/csv; charset=utf-8"); response["Content-Disposition"] = f'attachment; filename="relatorio-{report_name}.csv"'; response.write("\\ufeff")
    start, end = filter_period(request); company = current_company(request.user); writer = csv.writer(response); writer.writerow(["Relatório", report_name, "Período", start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")])
    if report_name == "abastecimentos":
        writer.writerow(["Caminhão", "Data", "Cidade", "Estado", "Litros", "Valor", "R$/L", "Km/L"])
        for item in Fueling.objects.filter(company=company, fueled_at__date__range=(start, end)).select_related("truck"):
            writer.writerow([item.truck.identification, item.fueled_at.strftime("%d/%m/%Y %H:%M"), item.city, item.state, item.liters, item.total_amount, item.price_per_liter, item.km_per_liter or ""])
    elif report_name == "trechos":
        writer.writerow(["Origem", "Destino", "Caminhão", "Motorista", "Status", "Km"])
        for item in Trip.objects.filter(company=company, started_at__date__range=(start, end)).select_related("truck", "driver"):
            writer.writerow([item.origin, item.destination, item.truck.identification, item.driver.name, item.get_status_display(), item.distance_km])
    elif report_name == "custos":
        writer.writerow(["Caminhão", "Combustível", "Manutenção", "Pneus", "Financiamento", "Fixos", "Remuneração", "Km", "Total", "Custo por km"])
        truck_queryset = Truck.objects.filter(company=company)
        if request.GET.get("truck"):
            truck_queryset = truck_queryset.filter(pk=request.GET["truck"])
        for truck in truck_queryset:
            costs = truck_costs(company, start, end, truck.pk)
            distance = Trip.objects.filter(company=company, truck=truck, status=Trip.FINISHED, started_at__date__range=(start, end)).aggregate(value=Sum("distance_km"))["value"] or Decimal("0")
            total = sum(costs.values(), Decimal("0"))
            writer.writerow([truck.identification, costs["fuel"], costs["maintenance"], costs["tires"], costs["financing"], costs["fixed"], costs["remuneration"], distance, total, total / distance if distance else 0])
    elif report_name == "manutencoes":
        writer.writerow(["Caminhão", "Data", "Tipo", "Descrição", "Oficina", "Valor", "Status"])
        for item in Maintenance.objects.filter(company=company, date__range=(start, end)).select_related("truck"):
            writer.writerow([item.truck.identification, item.date.strftime("%d/%m/%Y"), item.get_maintenance_type_display(), item.description, item.workshop, item.amount, item.get_status_display()])
    elif report_name == "producao":
        writer.writerow(["Contrato", "Competência", "Caminhão", "Motorista", "Valor realizado", "Status"])
        for item in Production.objects.filter(company=company, competence__range=(start, end)).select_related("contract", "truck", "driver"):
            writer.writerow([item.contract.code, item.competence.strftime("%d/%m/%Y"), item.truck.identification if item.truck else "Rateio", item.driver.name if item.driver else "Rateio", item.realized_value, item.get_status_display()])
    elif report_name == "remuneracao":
        writer.writerow(["Motorista", "Competência", "Fixo", "Comissão", "Bônus km", "Bônus viagens", "Outros bônus", "Total"])
        for item in Remuneration.objects.filter(company=company, competence__range=(start, end)).select_related("driver"):
            writer.writerow([item.driver.name, item.competence.strftime("%m/%Y"), item.fixed_amount, item.commission_amount, item.km_bonus, item.trips_bonus, item.other_bonus, item.total_amount])
    elif report_name == "resultado":
        writer.writerow(["Caminhão", "Receita realizada", "Custos", "Km", "Custo por km", "Resultado operacional estimado", "Margem estimada (%)"])
        allocation = production_allocation(company, start, end)
        truck_queryset = Truck.objects.filter(company=company)
        if request.GET.get("truck"):
            truck_queryset = truck_queryset.filter(pk=request.GET["truck"])
        for truck in truck_queryset:
            costs = truck_costs(company, start, end, truck.pk); total = sum(costs.values(), Decimal("0")); revenue = allocation.get(truck.pk, Decimal("0")); distance = Trip.objects.filter(company=company, truck=truck, status=Trip.FINISHED, started_at__date__range=(start, end)).aggregate(value=Sum("distance_km"))["value"] or Decimal("0"); result = revenue - total; writer.writerow([truck.identification, revenue, total, distance, total / distance if distance else 0, result, result / revenue * Decimal("100") if revenue else 0])
    else:
        writer.writerow(["Observação", "Relatório não encontrado"])
    return response
