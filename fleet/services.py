from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum

from .models import Driver, FixedCost, Fueling, Maintenance, Production, Remuneration, RemunerationRule, TireExpense, Trip


MONEY = Decimal("0.01")


def period_months(start, end):
    return max((end.year - start.year) * 12 + end.month - start.month + 1, 1)


def prorated_monthly_amount(monthly_amount, start, end, valid_from=None, valid_until=None):
    """Recognize a monthly cost only for the days covered by the period.

    This is an accrual allocation, so a dashboard filtered to a few days does
    not show an entire month of fixed costs or financing installments.
    """
    effective_start = max(start, valid_from or start)
    effective_end = min(end, valid_until or end)
    if effective_end < effective_start:
        return Decimal("0")

    total = Decimal("0")
    cursor = effective_start.replace(day=1)
    while cursor <= effective_end:
        last_day = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        covered_start = max(effective_start, cursor)
        covered_end = min(effective_end, last_day)
        covered_days = (covered_end - covered_start).days + 1
        total += Decimal(monthly_amount) * Decimal(covered_days) / Decimal(last_day.day)
        cursor = last_day + timedelta(days=1)
    return total


def month_bounds(competence):
    start = competence.replace(day=1)
    return start, competence.replace(day=monthrange(competence.year, competence.month)[1])


def round_money(value):
    return Decimal(value or 0).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_driver_remuneration(driver, competence):
    start, end = month_bounds(competence)
    trips = Trip.objects.filter(driver=driver, started_at__date__gte=start, started_at__date__lte=end, status=Trip.FINISHED)
    productions = Production.objects.filter(
        driver=driver,
        competence__gte=start,
        competence__lte=end,
        status=Production.APPROVED,
    )
    realized = productions.aggregate(total=Sum("realized_value"))["total"] or Decimal("0")
    km = trips.aggregate(total=Sum("distance_km"))["total"] or Decimal("0")
    trip_count = trips.count()
    rules = RemunerationRule.objects.filter(company=driver.company, active=True, effective_from__lte=end).filter(
        effective_until__isnull=True
    ) | RemunerationRule.objects.filter(company=driver.company, active=True, effective_from__lte=end, effective_until__gte=start)
    # Specificity (driver + contract) and priority: select the strongest applicable rule
    active_contract_ids = set(productions.values_list("contract_id", flat=True))
    active_contract_ids.update(trips.values_list("contract_id", flat=True))
    applicable = []
    for rule in rules.distinct():
        if rule.driver_id not in (None, driver.id):
            continue
        if rule.contract_id and rule.contract_id not in active_contract_ids:
            continue
        applicable.append(rule)
    applicable.sort(key=lambda r: ((r.driver_id is not None) + (r.contract_id is not None), r.priority, r.effective_from), reverse=True)
    rule = applicable[0] if applicable else None
    bonus_rules = [item for item in applicable if item.bonus_type != RemunerationRule.NO_BONUS]
    fixed = driver.monthly_fixed
    commission_base = realized
    commission_percent = Decimal("0")
    commission = Decimal("0")
    km_bonus = Decimal("0")
    trips_bonus = Decimal("0")
    other_bonus = Decimal("0")
    notes = [f"Período: {start:%d/%m/%Y} a {end:%d/%m/%Y}", f"Quilômetros: {km}", f"Viagens: {trip_count}", f"Valor realizado: R$ {realized}"]
    if rule:
        fixed = rule.fixed_monthly or fixed
        if rule.commission_base == RemunerationRule.DISTANCE:
            commission_base = km
        elif rule.commission_base == RemunerationRule.TRIPS:
            commission_base = Decimal(trip_count)
        commission_percent = rule.commission_percent
        commission = commission_base * commission_percent / Decimal("100")
        for bonus_rule in bonus_rules:
            if bonus_rule.bonus_type == RemunerationRule.KM_BONUS and bonus_rule.bonus_km_limit and km >= bonus_rule.bonus_km_limit:
                km_bonus += bonus_rule.bonus_amount
            elif bonus_rule.bonus_type == RemunerationRule.TRIP_BONUS and bonus_rule.bonus_trip_limit and trip_count >= bonus_rule.bonus_trip_limit:
                trips_bonus += bonus_rule.bonus_amount
            elif bonus_rule.bonus_type == RemunerationRule.FIXED_BONUS:
                other_bonus += bonus_rule.bonus_amount
            elif bonus_rule.bonus_type == RemunerationRule.PERCENT_BONUS:
                other_bonus += realized * bonus_rule.bonus_percent / Decimal("100")
        notes.append(f"Regra utilizada: {rule}")
    notes.extend([f"Fixo: R$ {fixed}", f"Base: {commission_base} · Comissão: {commission_percent}% = R$ {commission}", f"Bônus km: R$ {km_bonus}", f"Bônus viagens: R$ {trips_bonus}", f"Outros bônus: R$ {other_bonus}"])
    total = fixed + commission + km_bonus + trips_bonus + other_bonus
    return {
        "fixed_amount": round_money(fixed), "commission_base_value": round_money(commission_base), "commission_percent": commission_percent,
        "commission_amount": round_money(commission), "km_bonus": round_money(km_bonus), "trips_bonus": round_money(trips_bonus),
        "other_bonus": round_money(other_bonus), "total_amount": round_money(total), "calculation_notes": "\n".join(notes),
        "km": km, "trip_count": trip_count, "realized": realized,
    }


def calculate_fixed_cost_allocation(company, start, end):
    """Allocate fixed driver salaries by truck distance, falling back to trips."""
    trips = Trip.objects.filter(company=company, started_at__date__gte=start, started_at__date__lte=end, status=Trip.FINISHED)
    distance_by_truck = {row["truck_id"]: row["total"] or Decimal("0") for row in trips.values("truck_id").annotate(total=Sum("distance_km"))}
    trip_by_truck = {row["truck_id"]: row["total"] for row in trips.values("truck_id").annotate(total=Count("id"))}
    total_distance = sum(distance_by_truck.values(), Decimal("0"))
    total_trips = sum(trip_by_truck.values()) or 0
    result = defaultdict(lambda: Decimal("0"))
    drivers = Driver.objects.filter(company=company, status=Driver.ACTIVE)
    for driver in drivers:
        fixed_amount = prorated_monthly_amount(driver.monthly_fixed, start, end)
        if total_distance:
            for truck_id, distance in distance_by_truck.items():
                result[truck_id] += fixed_amount * distance / total_distance
        elif total_trips:
            for truck_id, count in trip_by_truck.items():
                result[truck_id] += fixed_amount * Decimal(count) / Decimal(total_trips)
    return result


def truck_costs(company, start, end, truck_id=None):
    qs = {"company": company, "truck_id": truck_id} if truck_id else {"company": company}
    fuel = Fueling.objects.filter(**qs, fueled_at__date__gte=start, fueled_at__date__lte=end).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    maintenance = Maintenance.objects.filter(**qs, date__gte=start, date__lte=end).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    tires = TireExpense.objects.filter(**qs, date__gte=start, date__lte=end).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    fixed_base = FixedCost.objects.filter(company=company, valid_from__lte=end, active=True).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start))
    fixed = fixed_base.filter(Q(truck_id=truck_id) | Q(truck__isnull=True)) if truck_id else fixed_base
    fixed_total = sum(
        (
            prorated_monthly_amount(item.monthly_amount, start, end, item.valid_from, item.valid_until)
            for item in fixed
        ),
        Decimal("0"),
    )
    financing = Decimal("0")
    # Financing is a monthly cost; include each active record in a filtered month.
    for item in company.financing_set.filter(truck_id=truck_id) if truck_id else company.financing_set.all():
        if item.truck.financial_status == item.truck.FINANCED and item.start_date and item.start_date <= end and (not item.expected_end_date or item.expected_end_date >= start):
            financing += prorated_monthly_amount(
                item.monthly_payment,
                start,
                end,
                item.start_date,
                item.expected_end_date,
            )
    remuneration = remuneration_truck_allocation(company, start, end).get(truck_id, Decimal("0")) if truck_id else sum(remuneration_truck_allocation(company, start, end).values(), Decimal("0"))
    return {"fuel": fuel, "maintenance": maintenance, "tires": tires, "fixed": fixed_total, "financing": financing, "remuneration": remuneration}


def remuneration_truck_allocation(company, start, end, driver_ids=None):
    """Allocate each driver's monthly remuneration across the trucks they drove."""
    result = defaultdict(lambda: Decimal("0"))
    drivers = Driver.objects.filter(company=company, status=Driver.ACTIVE)
    if driver_ids:
        drivers = drivers.filter(pk__in=driver_ids)
    month = start.replace(day=1)
    while month <= end:
        month_end = month.replace(day=monthrange(month.year, month.month)[1])
        for driver in drivers:
            calculation = Remuneration.objects.filter(driver=driver, competence=month).first()
            total = calculation.total_amount if calculation else calculate_driver_remuneration(driver, month)["total_amount"]
            selected_start, selected_end = max(start, month), min(end, month_end)
            allocated_total = prorated_monthly_amount(total, selected_start, selected_end, month, month_end)
            trips = Trip.objects.filter(company=company, driver=driver, status=Trip.FINISHED, started_at__date__range=(selected_start, selected_end))
            by_truck = list(trips.values("truck_id").annotate(distance=Sum("distance_km"), trips=Count("id")))
            total_distance = sum((row["distance"] or Decimal("0") for row in by_truck), Decimal("0"))
            total_trips = sum((row["trips"] or 0 for row in by_truck))
            for row in by_truck:
                weight = (row["distance"] / total_distance) if total_distance else Decimal(row["trips"] or 0) / Decimal(total_trips or 1)
                result[row["truck_id"]] += allocated_total * weight
        month = month_end + timedelta(days=1)
    return result


def production_allocation(company, start, end):
    """Return production distributed by truck, including contract-only entries.

    A production record without a truck is allocated to the trucks that carried
    the same contract in the competence period, by distance and then by trip
    count when distance is unavailable.
    """
    values = defaultdict(lambda: Decimal("0"))
    productions = Production.objects.filter(company=company, competence__range=(start, end), status=Production.APPROVED)
    for production in productions.filter(truck__isnull=False):
        values[production.truck_id] += production.realized_value
    for production in productions.filter(truck__isnull=True):
        trips = Trip.objects.filter(company=company, contract=production.contract, status=Trip.FINISHED, started_at__date__range=(start, end))
        by_truck = list(trips.values("truck_id").annotate(distance=Sum("distance_km"), trips=Count("id")))
        total_distance = sum((row["distance"] or Decimal("0") for row in by_truck), Decimal("0"))
        total_trips = sum(row["trips"] or 0 for row in by_truck)
        for row in by_truck:
            weight = (row["distance"] / total_distance) if total_distance else (Decimal(row["trips"] or 0) / Decimal(total_trips or 1))
            values[row["truck_id"]] += production.realized_value * weight
    return values
