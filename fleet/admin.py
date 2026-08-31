from django.contrib import admin

from .models import (
    AuditLog, CashEntry, Company, Contract, Driver, Financing, FixedCost, Fueling, Maintenance, MaintenancePlan,
    Occurrence, Production, Remuneration, RemunerationRule, Stop, TireExpense, Trip,
    Truck, UserProfile, VehicleChecklist,
)


class CompanyScopedAdmin(admin.ModelAdmin):
    list_display = ("__str__", "company", "created_at", "updated_at")
    list_filter = ("company",)
    search_fields = ("company__name",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        profile = getattr(request.user, "fleet_profile", None)
        return queryset.filter(company=profile.company) if profile else queryset.none()

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "company_id") and not obj.company_id:
            obj.company = request.user.fleet_profile.company
        if hasattr(obj, "created_by_id") and not obj.created_by_id:
            obj.created_by = request.user
        if hasattr(obj, "updated_by_id"):
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "active", "created_at")
    search_fields = ("name", "code")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "phone")
    list_filter = ("company", "role")
    search_fields = ("user__username", "user__first_name", "user__last_name")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        profile = getattr(request.user, "fleet_profile", None)
        return queryset.filter(company=profile.company) if profile else queryset.none()


@admin.register(Truck)
class TruckAdmin(CompanyScopedAdmin):
    list_display = ("identification", "simulated_plate", "model", "status", "financial_status", "current_odometer", "company")
    list_filter = ("company", "status", "financial_status", "fuel_type")
    search_fields = ("identification", "simulated_plate", "model", "brand")


@admin.register(Financing)
class FinancingAdmin(CompanyScopedAdmin):
    list_display = ("truck", "monthly_payment", "installments_paid", "installments", "approximate_balance", "company")
    search_fields = ("truck__identification", "financial_institution")


@admin.register(Driver)
class DriverAdmin(CompanyScopedAdmin):
    list_display = ("name", "user", "status", "monthly_fixed", "company")
    list_filter = ("company", "status")
    search_fields = ("name", "user__username", "phone")


@admin.register(Contract)
class ContractAdmin(CompanyScopedAdmin):
    list_display = ("code", "client_name", "status", "production_type", "contracted_value", "company")
    list_filter = ("company", "status", "production_type")
    search_fields = ("code", "client_name")


@admin.register(Trip)
class TripAdmin(CompanyScopedAdmin):
    list_display = ("origin", "destination", "truck", "driver", "status", "distance_km", "started_at", "company")
    list_filter = ("company", "status", "truck", "driver")
    search_fields = ("origin", "destination", "truck__identification", "driver__name")


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = ("location", "trip", "started_at", "ended_at")
    search_fields = ("location", "reason", "trip__origin", "trip__destination")


@admin.register(Fueling)
class FuelingAdmin(CompanyScopedAdmin):
    list_display = ("truck", "fueled_at", "city", "liters", "total_amount", "price_per_liter", "km_per_liter", "company")
    list_filter = ("company", "fuel_type", "tank_full", "city", "state")
    search_fields = ("truck__identification", "station", "city")


@admin.register(VehicleChecklist)
class VehicleChecklistAdmin(CompanyScopedAdmin):
    list_display = ("checked_at", "truck", "driver", "has_issue", "company")
    list_filter = ("company", "truck", "driver")
    search_fields = ("truck__identification", "driver__name", "notes")


@admin.register(Maintenance)
class MaintenanceAdmin(CompanyScopedAdmin):
    list_display = ("truck", "maintenance_type", "date", "amount", "status", "company")
    list_filter = ("company", "maintenance_type", "status", "truck")
    search_fields = ("truck__identification", "description", "workshop")


@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(CompanyScopedAdmin):
    list_display = ("truck", "title", "maintenance_type", "next_due_date", "next_due_odometer", "active", "company")
    list_filter = ("company", "active", "maintenance_type", "truck")
    search_fields = ("truck__identification", "title")


@admin.register(CashEntry)
class CashEntryAdmin(CompanyScopedAdmin):
    list_display = ("due_date", "entry_type", "description", "amount", "status", "truck", "contract", "company")
    list_filter = ("company", "entry_type", "status", "due_date")
    search_fields = ("description", "category", "reference", "truck__identification", "contract__code")


@admin.register(TireExpense)
class TireExpenseAdmin(CompanyScopedAdmin):
    list_display = ("truck", "date", "quantity", "amount", "supplier", "company")
    list_filter = ("company", "truck")


@admin.register(FixedCost)
class FixedCostAdmin(CompanyScopedAdmin):
    list_display = ("description", "category", "truck", "monthly_amount", "active", "company")
    list_filter = ("company", "category", "active")


@admin.register(Production)
class ProductionAdmin(CompanyScopedAdmin):
    list_display = ("contract", "competence", "realized_value", "truck", "driver", "status", "company")
    list_filter = ("company", "status", "contract", "truck", "driver")
    search_fields = ("contract__code", "contract__client_name")


@admin.register(RemunerationRule)
class RemunerationRuleAdmin(CompanyScopedAdmin):
    list_display = ("driver", "contract", "effective_from", "priority", "commission_percent", "bonus_type", "active", "company")
    list_filter = ("company", "active", "bonus_type", "commission_base")


@admin.register(Remuneration)
class RemunerationAdmin(CompanyScopedAdmin):
    list_display = ("driver", "competence", "total_amount", "status", "company")
    list_filter = ("company", "status", "driver")


@admin.register(Occurrence)
class OccurrenceAdmin(CompanyScopedAdmin):
    list_display = ("title", "truck", "driver", "occurred_at", "status", "company")
    list_filter = ("company", "status")
    search_fields = ("title", "description", "truck__identification", "driver__name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "model_name", "object_id", "user", "company")
    list_filter = ("company", "action", "model_name")
    search_fields = ("model_name", "object_id", "reason", "user__username")
    readonly_fields = [field.name for field in AuditLog._meta.fields]
