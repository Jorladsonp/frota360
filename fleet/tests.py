from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.conf import settings
from django.core import management
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AuditLog, CashEntry, Company, Contract, Driver, Fueling, Maintenance, MaintenancePlan, Occurrence, Production, RemunerationRule, Stop, Trip, Truck, UserProfile, VehicleChecklist
from .services import calculate_driver_remuneration, calculate_fixed_cost_allocation, prorated_monthly_amount, truck_costs
from .views import dashboard_metrics


class FleetTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa A", code="empresa-a")
        self.other_company = Company.objects.create(name="Empresa B", code="empresa-b")
        self.manager_user = User.objects.create_user("gestor", password="senha-segura")
        self.driver_user = User.objects.create_user("motorista", password="senha-segura")
        self.other_user = User.objects.create_user("outro", password="senha-segura")
        UserProfile.objects.create(user=self.manager_user, company=self.company, role=UserProfile.MANAGER)
        UserProfile.objects.create(user=self.driver_user, company=self.company, role=UserProfile.DRIVER)
        UserProfile.objects.create(user=self.other_user, company=self.other_company, role=UserProfile.DRIVER)
        self.driver = Driver.objects.create(company=self.company, name="Motorista Teste", user=self.driver_user, monthly_fixed=Decimal("2000"))
        self.other_driver = Driver.objects.create(company=self.other_company, name="Outro Motorista", user=self.other_user)
        self.truck = Truck.objects.create(company=self.company, identification="TEST-001", simulated_plate="TST-001", brand="Demo", model="Modelo", current_odometer=Decimal("1000"))
        self.other_truck = Truck.objects.create(company=self.other_company, identification="TEST-001", simulated_plate="TST-002", brand="Demo", model="Modelo", current_odometer=Decimal("1000"))
        self.contract = Contract.objects.create(company=self.company, code="CTR-TEST", client_name="Cliente Teste", start_date=date.today())
        self.other_contract = Contract.objects.create(company=self.other_company, code="CTR-TEST", client_name="Outro Cliente", start_date=date.today())

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def finished_trip(self, distance=100):
        started = timezone.now() - timedelta(hours=2)
        trip = Trip.objects.create(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="Origem", destination="Destino", start_odometer=Decimal("1000"), started_at=started, status=Trip.IN_PROGRESS)
        trip.finish(Decimal("1000") + Decimal(str(distance)))
        trip.save()
        return trip


class AuthenticationAndTenantTests(FleetTestCase):
    def test_local_preview_is_a_trusted_csrf_origin(self):
        self.assertIn("https://localhost:8000", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn("http://localhost:8000", settings.CSRF_TRUSTED_ORIGINS)

    def test_login_redirects_by_profile(self):
        client = Client()
        response = client.post(reverse("login"), {"username": "gestor", "password": "senha-segura"})
        self.assertRedirects(response, reverse("dashboard"))
        client.logout()
        response = client.post(reverse("login"), {"username": "motorista", "password": "senha-segura"})
        self.assertRedirects(response, reverse("driver_dashboard"))

    def test_manager_and_driver_permissions(self):
        self.assertEqual(self.login(self.manager_user).get(reverse("dashboard")).status_code, 200)
        driver_client = self.login(self.driver_user)
        response = driver_client.get(reverse("truck_list"))
        self.assertRedirects(response, reverse("driver_dashboard"))
        self.assertEqual(driver_client.get(reverse("driver_dashboard")).status_code, 200)

    def test_dashboard_embeds_valid_json_for_all_charts(self):
        response = self.login(self.manager_user).get(reverse("dashboard"))
        page = response.content.decode()
        self.assertIn('const chartData={"labels"', page)
        self.assertIn('const breakdownData={"truck_labels"', page)

    def test_driver_experience_is_installable_as_a_pwa(self):
        response = self.login(self.driver_user).get(reverse("driver_dashboard"))
        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "driver-app")
        self.assertContains(response, "fleet/app.css?v=")
        self.assertContains(response, "fleet/app.js?v=")
        worker = self.login(self.driver_user).get(reverse("pwa_service_worker"))
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker["Service-Worker-Allowed"], "/")
        self.assertContains(worker, "frota360-static-v2")
        self.assertContains(worker, "fetch(request)")

    def test_driver_dashboard_has_a_clear_logout_and_action_states(self):
        response = self.login(self.driver_user).get(reverse("driver_dashboard"))
        page = response.content.decode()
        self.assertContains(response, "Sair da conta")
        self.assertContains(response, "O que você precisa registrar?")
        self.assertIn('aria-disabled="true"', page)
        self.assertNotIn('data-sidebar-collapse', page)

    def test_dashboard_prioritizes_alerts_and_uses_operational_health_status(self):
        response = self.login(self.manager_user).get(reverse("dashboard"))
        page = response.content.decode()
        self.assertLess(page.index("attention-panel"), page.index("filter-bar"))
        self.assertContains(response, "Em operação")
        self.assertContains(response, "Inativos")
        self.assertContains(response, "Status da frota")
        self.assertIn('data-sidebar-collapse', page)
        self.assertIn('class="col-12"', page)

    def test_financial_pages_render_interactive_chart_sections(self):
        client = self.login(self.manager_user)
        pages = (
            ("production_list", "productionMonthlyChart"),
            ("fixed_cost_list", "fixedCategoryChart"),
            ("remuneration_view", "remunerationHistoryChart"),
        )
        for route_name, chart_id in pages:
            response = client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, chart_id)

    def test_manager_has_operational_and_fueling_command_centers(self):
        client = self.login(self.manager_user)
        operation = client.get(reverse("operation_dashboard"), {"start": timezone.localdate() - timedelta(days=7), "end": timezone.localdate()})
        self.assertEqual(operation.status_code, 200)
        self.assertContains(operation, "operationDailyChart")
        self.assertContains(operation, "data-async-filter")
        fuel = client.get(reverse("fueling_list"), {"start": timezone.localdate() - timedelta(days=7), "end": timezone.localdate()})
        self.assertEqual(fuel.status_code, 200)
        self.assertContains(fuel, "fuelMonthlyChart")
        self.assertContains(fuel, "Preço médio ponderado")

    def test_manager_can_manage_preventive_maintenance_and_cashflow(self):
        client = self.login(self.manager_user)
        plan = client.post(reverse("maintenance_plan_create"), {"truck": self.truck.pk, "maintenance_type": Maintenance.OIL, "title": "Troca de óleo", "interval_days": "180", "interval_km": "15000", "next_due_date": timezone.localdate() + timedelta(days=30), "next_due_odometer": "15000", "active": "on", "notes": ""})
        self.assertRedirects(plan, reverse("maintenance_list"))
        self.assertTrue(MaintenancePlan.objects.filter(company=self.company, truck=self.truck).exists())
        entry = client.post(reverse("cash_entry_create"), {"entry_type": CashEntry.PAYABLE, "category": "Oficina", "description": "Revisão programada", "amount": "850.00", "due_date": timezone.localdate() + timedelta(days=7), "status": CashEntry.PENDING, "truck": self.truck.pk, "contract": "", "reference": "OS-1", "notes": ""})
        self.assertRedirects(entry, reverse("cashflow_view"))
        cash = CashEntry.objects.get(company=self.company, reference="OS-1")
        self.assertRedirects(client.post(reverse("cash_entry_transition", args=[cash.pk, "approve"])), reverse("cashflow_view"))
        cash.refresh_from_db(); self.assertEqual(cash.status, CashEntry.APPROVED)
        self.assertRedirects(client.post(reverse("cash_entry_transition", args=[cash.pk, "pay"])), reverse("cashflow_view"))
        cash.refresh_from_db(); self.assertEqual(cash.status, CashEntry.PAID)

    def test_dashboard_and_reports_expose_chart_filter_dimensions(self):
        client = self.login(self.manager_user)
        dashboard = client.get(reverse("dashboard"))
        dashboard_page = dashboard.content.decode()
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn('"starts":', dashboard_page)
        self.assertIn('"truck_ids":', dashboard_page)
        costs = client.get(reverse("report_view", args=["custos"]))
        costs_page = costs.content.decode()
        self.assertEqual(costs.status_code, 200)
        self.assertIn('"keys":', costs_page)
        self.assertIn('"ids":', costs_page)
        result = client.get(reverse("report_view", args=["resultado"]))
        self.assertEqual(result.status_code, 200)
        self.assertIn('"starts":', result.content.decode())

    def test_manager_can_create_individual_driver_access(self):
        client = self.login(self.manager_user)
        response = client.post(reverse("driver_create"), {"name": "Novo Motorista", "access_username": "novo_motorista", "access_password": "SenhaForte!2026", "phone": "(00) 90000-0000", "status": Driver.ACTIVE, "monthly_fixed": "1800", "notes": ""})
        self.assertRedirects(response, reverse("driver_list"))
        new_user = User.objects.get(username="novo_motorista")
        self.assertEqual(new_user.fleet_profile.company, self.company)
        self.assertEqual(new_user.fleet_profile.role, UserProfile.DRIVER)
        self.assertTrue(Driver.objects.filter(name="Novo Motorista", user=new_user, company=self.company).exists())

    def test_records_are_scoped_to_company(self):
        other_trip = Trip.objects.create(company=self.other_company, truck=self.other_truck, driver=self.other_driver, contract=self.other_contract, origin="Outra", destination="Cidade", start_odometer=1000, status=Trip.PLANNED)
        client = self.login(self.manager_user)
        self.assertEqual(client.get(reverse("trip_detail", args=[other_trip.pk])).status_code, 404)
        self.assertNotContains(client.get(reverse("trip_list")), "Outra")


class TripTests(FleetTestCase):
    def test_create_and_finish_trip_calculates_distance_and_duration(self):
        client = self.login(self.driver_user)
        response = client.post(reverse("trip_start"), {"truck": self.truck.pk, "contract": self.contract.pk, "origin": "São Paulo", "destination": "Campinas", "start_odometer": "1000", "notes": ""})
        self.assertRedirects(response, reverse("driver_dashboard"))
        trip = Trip.objects.get(company=self.company)
        self.assertEqual(trip.status, Trip.IN_PROGRESS)
        response = client.post(reverse("trip_finish", args=[trip.pk]), {"end_odometer": "1125", "notes": "Chegada registrada"})
        self.assertRedirects(response, reverse("driver_dashboard"))
        trip.refresh_from_db()
        self.assertEqual(trip.distance_km, Decimal("125.0"))
        self.assertIsNotNone(trip.duration)
        self.assertEqual(trip.status, Trip.FINISHED)

    def test_invalid_odometer_and_open_trip_rules(self):
        with self.assertRaises(ValidationError):
            trip = Trip(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="A", destination="B", start_odometer=900)
            trip.start()
        trip = Trip(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="A", destination="B", start_odometer=1000)
        trip.start(); trip.save()
        second = Trip(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="C", destination="D", start_odometer=1000)
        with self.assertRaises(ValidationError):
            second.start()
        with self.assertRaises(ValidationError):
            trip.finish(Decimal("999"))

    def test_driver_can_navigate_every_operational_screen_from_the_panel(self):
        active_trip = Trip.objects.create(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="São Paulo", destination="Campinas", start_odometer=Decimal("1000"), started_at=timezone.now() - timedelta(minutes=10), status=Trip.IN_PROGRESS)
        client = self.login(self.driver_user)
        paths = (
            reverse("driver_dashboard"), reverse("trip_list"), reverse("fueling_list"), reverse("checklist_list"),
            reverse("driver_remuneration_view"), reverse("trip_detail", args=[active_trip.pk]), reverse("trip_start"),
            reverse("trip_finish", args=[active_trip.pk]), reverse("stop_create", args=[active_trip.pk]),
            reverse("fueling_create"), reverse("checklist_create"), reverse("occurrence_create"),
        )
        for path in paths:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, reverse("driver_dashboard"))
            self.assertContains(response, "Sair da conta")

    def test_driver_forms_default_to_now_and_reject_records_before_trip_start(self):
        started_at = timezone.now() - timedelta(minutes=10)
        active_trip = Trip.objects.create(company=self.company, truck=self.truck, driver=self.driver, contract=self.contract, origin="São Paulo", destination="Campinas", start_odometer=Decimal("1000"), started_at=started_at, status=Trip.IN_PROGRESS)
        client = self.login(self.driver_user)
        fuel_page = client.get(reverse("fueling_create"))
        stop_page = client.get(reverse("stop_create", args=[active_trip.pk]))
        self.assertIsNotNone(fuel_page.context["form"]["fueled_at"].value())
        self.assertIsNotNone(stop_page.context["form"]["started_at"].value())
        before_start = timezone.localtime(started_at - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M")
        stop_response = client.post(reverse("stop_create", args=[active_trip.pk]), {"location": "Posto", "started_at": before_start, "ended_at": "", "reason": "Descanso", "odometer": "1000", "notes": ""})
        self.assertEqual(stop_response.status_code, 200)
        self.assertContains(stop_response, "A pausa não pode começar antes do início da viagem.")
        self.assertFalse(active_trip.stops.exists())
        fuel_response = client.post(reverse("fueling_create"), {"truck": self.truck.pk, "trip": active_trip.pk, "fueled_at": before_start, "city": "Campinas", "state": "SP", "station": "Posto Demo", "fuel_type": Truck.FUEL_DIESEL, "odometer": "1000", "liters": "20", "total_amount": "120", "tank_full": "", "notes": ""})
        self.assertEqual(fuel_response.status_code, 200)
        self.assertContains(fuel_response, "O abastecimento não pode ser anterior ao início da viagem.")
        self.assertFalse(Fueling.objects.filter(company=self.company).exists())

    def test_finished_trip_is_blocked_and_reopen_is_audited(self):
        trip = self.finished_trip()
        trip.origin = "Alteração indevida"
        with self.assertRaises(ValidationError):
            trip.save()
        client = self.login(self.manager_user)
        response = client.post(reverse("reopen_trip", args=[trip.pk]), {"reason": "Corrigir origem informada"})
        self.assertRedirects(response, reverse("trip_detail", args=[trip.pk]))
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.REOPENED)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.REOPEN, object_id=str(trip.pk), reason="Corrigir origem informada").exists())

    def test_driver_can_submit_a_vehicle_checklist(self):
        client = self.login(self.driver_user)
        response = client.post(
            reverse("checklist_create"),
            {
                "truck": self.truck.pk,
                "tires_ok": "on",
                "lights_ok": "on",
                "oil_ok": "on",
                "brakes_ok": "on",
                "documents_ok": "on",
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("driver_dashboard"))
        self.assertTrue(VehicleChecklist.objects.filter(company=self.company, driver=self.driver, truck=self.truck).exists())

    def test_manager_can_plan_and_driver_can_start_the_planned_trip(self):
        manager = self.login(self.manager_user)
        planned_start = timezone.localtime(timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        planned_end = timezone.localtime(timezone.now() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M")
        response = manager.post(reverse("trip_plan_create"), {"truck": self.truck.pk, "driver": self.driver.pk, "contract": self.contract.pk, "origin": "São Paulo", "destination": "Santos", "planned_start_at": planned_start, "planned_end_at": planned_end, "cargo_description": "Carga prioritária", "cargo_weight": "1200.50", "delivery_reference": "NF-123", "start_odometer": "1000", "notes": "Carga prioritária"})
        self.assertRedirects(response, reverse("trip_list"))
        trip = Trip.objects.get(company=self.company, origin="São Paulo", status=Trip.PLANNED)
        self.assertEqual(trip.cargo_description, "Carga prioritária")
        self.assertEqual(trip.delivery_reference, "NF-123")
        self.assertIsNotNone(trip.planned_end_at)
        driver = self.login(self.driver_user)
        response = driver.post(reverse("trip_start_planned", args=[trip.pk]), {"start_odometer": "1000", "notes": ""})
        self.assertRedirects(response, reverse("driver_dashboard"))
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.IN_PROGRESS)


class CalculationTests(FleetTestCase):
    def test_fueling_price_and_km_per_liter(self):
        first = Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="São Paulo", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1000, liters=Decimal("20"), total_amount=Decimal("100"), tank_full=True)
        second = Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="Campinas", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1100, liters=Decimal("20"), total_amount=Decimal("120"), tank_full=True)
        self.assertEqual(first.price_per_liter, Decimal("5.000"))
        self.assertEqual(second.price_per_liter, Decimal("6.000"))
        self.assertEqual(second.km_per_liter, Decimal("5"))
        no_full = Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="Jundiaí", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1110, liters=Decimal("5"), total_amount=Decimal("30"), tank_full=False)
        self.assertIsNone(no_full.km_per_liter)

    def test_full_tank_consumption_includes_intermediate_refueling(self):
        started_at = timezone.now() - timedelta(hours=3)
        Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="São Paulo", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1000, liters=Decimal("20"), total_amount=Decimal("100"), tank_full=True, fueled_at=started_at)
        Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="Campinas", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1050, liters=Decimal("10"), total_amount=Decimal("60"), tank_full=False, fueled_at=started_at + timedelta(hours=1))
        full_tank = Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="Jundiaí", state="SP", station="Posto Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1100, liters=Decimal("10"), total_amount=Decimal("60"), tank_full=True, fueled_at=started_at + timedelta(hours=2))
        self.assertEqual(full_tank.km_per_liter, Decimal("5"))

    def test_monthly_values_are_prorated_to_the_selected_days(self):
        self.assertEqual(
            prorated_monthly_amount(Decimal("3100"), date(2026, 3, 10), date(2026, 3, 19)),
            Decimal("1000"),
        )

    def test_commission_is_based_on_realized_value_and_km_bonus(self):
        trip = self.finished_trip(600)
        Production.objects.create(company=self.company, contract=self.contract, competence=timezone.localdate().replace(day=1), trip=trip, truck=self.truck, driver=self.driver, realized_value=Decimal("20000"), status=Production.APPROVED)
        RemunerationRule.objects.create(company=self.company, driver=self.driver, effective_from=timezone.localdate() - timedelta(days=30), commission_percent=Decimal("5"), commission_base=RemunerationRule.REALIZED, fixed_monthly=Decimal("2000"), bonus_type=RemunerationRule.KM_BONUS, bonus_km_limit=500, bonus_amount=Decimal("300"))
        result = calculate_driver_remuneration(self.driver, timezone.localdate())
        self.assertEqual(result["commission_amount"], Decimal("1000.00"))
        self.assertEqual(result["km_bonus"], Decimal("300.00"))
        self.assertEqual(result["total_amount"], Decimal("3300.00"))

    def test_trip_bonus_and_fixed_cost_allocation(self):
        self.finished_trip(100)
        RemunerationRule.objects.create(company=self.company, driver=self.driver, effective_from=timezone.localdate() - timedelta(days=30), commission_base=RemunerationRule.TRIPS, bonus_type=RemunerationRule.TRIP_BONUS, bonus_trip_limit=1, bonus_amount=Decimal("100"))
        result = calculate_driver_remuneration(self.driver, timezone.localdate())
        self.assertEqual(result["trips_bonus"], Decimal("100.00"))
        allocation = calculate_fixed_cost_allocation(self.company, timezone.localdate() - timedelta(days=3), timezone.localdate())
        self.assertLess(allocation[self.truck.pk], Decimal("2000"))

    def test_operational_result_separates_costs(self):
        self.finished_trip(100)
        Fueling.objects.create(company=self.company, truck=self.truck, driver=self.driver, city="SP", state="SP", station="Demo", fuel_type=Truck.FUEL_DIESEL, odometer=1100, liters=20, total_amount=Decimal("100"))
        Maintenance.objects.create(company=self.company, truck=self.truck, maintenance_type=Maintenance.OIL, date=timezone.localdate(), description="Troca de óleo", amount=Decimal("50"))
        Production.objects.create(company=self.company, contract=self.contract, competence=timezone.localdate(), truck=self.truck, driver=self.driver, realized_value=Decimal("1000"), status=Production.APPROVED)
        result = dashboard_metrics(self.company, timezone.localdate() - timedelta(days=3), timezone.localdate())
        self.assertEqual(result["fuel"], Decimal("100"))
        self.assertEqual(result["maintenance"], Decimal("50"))
        expected_remuneration = prorated_monthly_amount(
            Decimal("2000"),
            timezone.localdate() - timedelta(days=3),
            timezone.localdate(),
        )
        self.assertEqual(result["remuneration"], expected_remuneration)
        self.assertEqual(result["result"], Decimal("850") - expected_remuneration)


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent_and_creates_expected_demo(self):
        management.call_command("seed_demo_data")
        seeded_models = (Company, Truck, Driver, Contract, Trip, Fueling, Stop, VehicleChecklist, MaintenancePlan, CashEntry, Occurrence, Production)
        counts = {model.__name__: model.objects.count() for model in seeded_models}
        management.call_command("seed_demo_data")
        for model_name, count in counts.items():
            model = {model.__name__: model for model in seeded_models}[model_name]
            self.assertEqual(model.objects.count(), count)
        self.assertEqual(Truck.objects.filter(financial_status=Truck.FINANCED).count(), 3)
        self.assertEqual(Truck.objects.filter(financial_status=Truck.PAID).count(), 2)
        self.assertGreater(Fueling.objects.filter(km_per_liter__isnull=False).count(), 0)
        self.assertGreater(VehicleChecklist.objects.count(), 0)
        self.assertGreater(MaintenancePlan.objects.count(), 0)
        self.assertGreater(CashEntry.objects.count(), 0)
