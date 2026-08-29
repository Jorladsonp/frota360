from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from fleet.models import (
    Company, Contract, Driver, Financing, FixedCost, Fueling, Maintenance, Production,
    Remuneration, RemunerationRule, TireExpense, Trip, Truck, UserProfile,
)
from fleet.services import calculate_driver_remuneration


class Command(BaseCommand):
    help = "Cria dados fictícios e idempotentes para demonstração da Gestão de Frotas."

    def handle(self, *args, **options):
        today = timezone.localdate()
        company, _ = Company.objects.get_or_create(code="demo", defaults={"name": "Transportadora Horizonte · Demo", "active": True})
        company.name = "Transportadora Horizonte · Demo"
        company.save(update_fields=["name", "active"])

        manager = self.user("gestor_demo", "Gestor", "Demo", "gestor.demo@example.invalid", "GestorDemo!2026", company, UserProfile.MANAGER)
        driver_users = []
        for index in range(1, 5):
            driver_users.append(self.user(f"motorista{index}_demo", f"Motorista {index}", "Demo", f"motorista{index}.demo@example.invalid", "MotoristaDemo!2026", company, UserProfile.DRIVER))

        drivers = []
        for index, user in enumerate(driver_users, 1):
            driver, _ = Driver.objects.get_or_create(company=company, name=f"Motorista Demo {index}", defaults={"user": user, "phone": f"(00) 90000-000{index}", "monthly_fixed": Decimal("2000.00"), "admission_date": today - timedelta(days=500)})
            driver.user = user
            driver.monthly_fixed = Decimal("2000.00") if index < 3 else Decimal("2200.00")
            driver.save()
            drivers.append(driver)

        trucks = []
        truck_specs = [("DEMO-001", "Volvo", "FH 540", Truck.FINANCED), ("DEMO-002", "Scania", "R 450", Truck.FINANCED), ("DEMO-003", "Mercedes-Benz", "Actros 2651", Truck.FINANCED), ("DEMO-004", "DAF", "XF 480", Truck.PAID), ("DEMO-005", "Iveco", "Hi-Way 600", Truck.PAID)]
        for index, (identification, brand, model, financial_status) in enumerate(truck_specs, 1):
            truck, _ = Truck.objects.get_or_create(company=company, identification=identification, defaults={"simulated_plate": f"DMO-{index:03d}", "brand": brand, "model": model, "year": 2021 + index % 3, "fuel_type": Truck.FUEL_DIESEL, "tank_capacity": Decimal("600"), "current_odometer": Decimal("100000") + index * 1000, "financial_status": financial_status, "status": Truck.OPERATING})
            truck.financial_status = financial_status
            truck.status = Truck.OPERATING
            truck.save()
            trucks.append(truck)
            if financial_status == Truck.FINANCED:
                Financing.objects.update_or_create(truck=truck, defaults={"company": company, "monthly_payment": Decimal("4850.00") + index * Decimal("150"), "financial_institution": "Banco Horizonte (fictício)", "start_date": today - timedelta(days=900), "expected_end_date": today + timedelta(days=700), "installments": 48, "installments_paid": 23, "approximate_balance": Decimal("125000.00") - index * Decimal("8500"), "created_by": manager, "updated_by": manager})

        contracts = []
        for index, client in enumerate(["Mercado Central Demo", "Indústria Vale Demo", "Agro Norte Demo"], 1):
            contract, _ = Contract.objects.get_or_create(company=company, code=f"CTR-DEMO-{index:03d}", defaults={"client_name": client, "description": "Contrato fictício para demonstração do MVP.", "contracted_value": Decimal("160000") + index * Decimal("35000"), "start_date": today - timedelta(days=365), "production_type": Contract.PER_KM if index == 1 else Contract.MANUAL, "value_per_km": Decimal("4.20") + index, "value_per_trip": Decimal("1800"), "status": Contract.ACTIVE, "created_by": manager, "updated_by": manager})
            contracts.append(contract)

        for truck in trucks:
            FixedCost.objects.get_or_create(company=company, truck=truck, category=FixedCost.INSURANCE, description=f"Seguro {truck.identification}", defaults={"monthly_amount": Decimal("780.00"), "valid_from": today - timedelta(days=365), "created_by": manager, "updated_by": manager})
            FixedCost.objects.get_or_create(company=company, truck=truck, category=FixedCost.TAX, description=f"IPVA {truck.identification}", defaults={"monthly_amount": Decimal("420.00"), "valid_from": today - timedelta(days=365), "created_by": manager, "updated_by": manager})

        self.history(company, manager, today, trucks, drivers, contracts)
        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados/atualizados com sucesso."))
        self.stdout.write("Gestor: gestor_demo / GestorDemo!2026")
        self.stdout.write("Motorista: motorista1_demo / MotoristaDemo!2026 (há mais três motoristas demo) ")

    def user(self, username, first_name, last_name, email, password, company, role):
        user, created = User.objects.get_or_create(username=username, defaults={"first_name": first_name, "last_name": last_name, "email": email, "is_active": True})
        user.first_name, user.last_name, user.email = first_name, last_name, email
        user.set_password(password)
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"company": company, "role": role})
        profile.company, profile.role = company, role
        profile.save(update_fields=["company", "role"])
        return user

    def history(self, company, manager, today, trucks, drivers, contracts):
        # Six monthly snapshots with coherent, entirely fictional operating data.
        for month_index in range(6, 0, -1):
            month = (today.replace(day=1) - timedelta(days=month_index * 30)).replace(day=1)
            for truck_index, truck in enumerate(trucks):
                driver = drivers[(truck_index + month_index) % len(drivers)]
                start_km = Decimal("100000") + truck_index * 1000 + Decimal((6 - month_index) * 850)
                trip_time = timezone.make_aware(datetime.combine(month.replace(day=min(8 + truck_index, 25)), time(7, 0)))
                trip_key = f"DEMO-SEED-TRIP-{truck.identification}-{month:%Y-%m}"
                trip, _ = Trip.objects.get_or_create(company=company, truck=truck, driver=driver, contract=contracts[truck_index % 3], started_at=trip_time, defaults={"origin": "São Paulo (demo)", "destination": "Campinas (demo)", "start_odometer": start_km, "end_odometer": start_km + Decimal("132.0"), "ended_at": trip_time + timedelta(hours=3, minutes=20), "distance_km": Decimal("132.0"), "duration": timedelta(hours=3, minutes=20), "status": Trip.FINISHED, "notes": trip_key, "created_by": manager, "updated_by": manager})
                trip.status = Trip.FINISHED
                trip.save(update_fields=["status"])
                fuel_time = trip_time + timedelta(hours=1)
                fueling, _ = Fueling.objects.get_or_create(company=company, truck=truck, fueled_at=fuel_time, notes=f"DEMO-SEED-FUEL-{truck.identification}-{month:%Y-%m}", defaults={"driver": driver, "trip": trip, "city": "Campinas", "state": "SP", "station": "Posto Horizonte Demo", "fuel_type": truck.fuel_type, "odometer": start_km + Decimal("132.0"), "liters": Decimal("260.00") + truck_index * 10, "total_amount": (Decimal("260.00") + truck_index * 10) * Decimal("5.89"), "tank_full": True, "created_by": manager, "updated_by": manager})
                fueling.driver, fueling.trip, fueling.city, fueling.state, fueling.station, fueling.fuel_type = driver, trip, "Campinas", "SP", "Posto Horizonte Demo", truck.fuel_type
                fueling.odometer, fueling.liters, fueling.total_amount, fueling.tank_full = start_km + Decimal("132.0"), Decimal("260.00") + truck_index * 10, (Decimal("260.00") + truck_index * 10) * Decimal("5.89"), True
                fueling.save()
                if month_index in (2, 5):
                    Maintenance.objects.get_or_create(company=company, truck=truck, date=month.replace(day=18), description=f"Revisão periódica {truck.identification}", defaults={"maintenance_type": Maintenance.PREVENTIVE, "odometer": start_km + Decimal("132"), "workshop": "Oficina Horizonte Demo", "amount": Decimal("1800") + truck_index * 250, "downtime_days": 1, "next_date": month.replace(day=18) + timedelta(days=180), "status": Maintenance.DONE, "created_by": manager, "updated_by": manager})
                if month_index in (3, 6):
                    TireExpense.objects.get_or_create(company=company, truck=truck, date=month.replace(day=12), notes=f"DEMO-SEED-TIRE-{truck.identification}-{month:%Y-%m}", defaults={"quantity": 2, "amount": Decimal("4200") + truck_index * 300, "odometer": start_km, "supplier": "Pneus Estrada Demo", "created_by": manager, "updated_by": manager})
                Production.objects.get_or_create(company=company, contract=contracts[truck_index % 3], competence=month, truck=truck, driver=driver, notes=f"DEMO-SEED-PRODUCTION-{truck.identification}-{month:%Y-%m}", defaults={"trip": trip, "realized_value": Decimal("12500") + truck_index * 850 + (6 - month_index) * 300, "status": Production.APPROVED, "created_by": manager, "updated_by": manager})

        RemunerationRule.objects.get_or_create(company=company, driver=drivers[0], contract=None, effective_from=today.replace(day=1) - timedelta(days=365), defaults={"commission_percent": Decimal("5.00"), "commission_base": RemunerationRule.REALIZED, "fixed_monthly": Decimal("2000.00"), "bonus_type": RemunerationRule.KM_BONUS, "bonus_km_limit": Decimal("500"), "bonus_amount": Decimal("350.00"), "priority": 10, "active": True, "created_by": manager, "updated_by": manager})
        RemunerationRule.objects.get_or_create(company=company, driver=drivers[1], contract=contracts[1], effective_from=today.replace(day=1) - timedelta(days=365), defaults={"commission_percent": Decimal("3.50"), "commission_base": RemunerationRule.REALIZED, "fixed_monthly": Decimal("2000.00"), "bonus_type": RemunerationRule.TRIP_BONUS, "bonus_trip_limit": 3, "bonus_amount": Decimal("250.00"), "priority": 20, "active": True, "created_by": manager, "updated_by": manager})

        for month_index in range(5, 0, -1):
            month = (today.replace(day=1) - timedelta(days=month_index * 30)).replace(day=1)
            for driver in drivers:
                calculation = calculate_driver_remuneration(driver, month)
                Remuneration.objects.update_or_create(company=company, driver=driver, competence=month, defaults={**{key: calculation[key] for key in ("fixed_amount", "commission_base_value", "commission_percent", "commission_amount", "km_bonus", "trips_bonus", "other_bonus", "total_amount", "calculation_notes")}, "status": Remuneration.APPROVED, "created_by": manager, "updated_by": manager})

        # Keep a live route visible in the driver experience, without duplicating it.
        live_driver, live_truck = drivers[0], trucks[0]
        if not Trip.objects.filter(company=company, status=Trip.IN_PROGRESS).exists():
            live = Trip.objects.create(company=company, truck=live_truck, driver=live_driver, contract=contracts[0], origin="Jundiaí (demo)", destination="Santos (demo)", start_odometer=live_truck.current_odometer, started_at=timezone.now(), status=Trip.IN_PROGRESS, notes="Trecho em andamento criado pelo seed demo.", created_by=manager, updated_by=manager)
            live.save()
