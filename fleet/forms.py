from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import CashEntry, Contract, Driver, Financing, FixedCost, Fueling, Maintenance, MaintenancePlan, Occurrence, Production, RemunerationRule, Stop, TireExpense, Trip, Truck, VehicleChecklist


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"form-control {existing}".strip()
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] += " form-select"
        self.fields.get("notes", None) and self.fields["notes"].widget.attrs.update(rows=3)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.company and hasattr(obj, "company_id"):
            obj.company = self.company
        if self.user:
            if not obj.pk and hasattr(obj, "created_by_id"):
                obj.created_by = self.user
            if hasattr(obj, "updated_by_id"):
                obj.updated_by = self.user
        if commit:
            obj.full_clean()
            obj.save()
            self.save_m2m()
        return obj


class TruckForm(StyledModelForm):
    class Meta:
        model = Truck
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"year": forms.NumberInput(attrs={"min": 1950, "max": 2100}), "current_odometer": forms.NumberInput(attrs={"step": "0.1"}), "tank_capacity": forms.NumberInput(attrs={"step": "0.01"})}


class FinancingForm(StyledModelForm):
    class Meta:
        model = Financing
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "expected_end_date": forms.DateInput(attrs={"type": "date"}), "monthly_payment": forms.NumberInput(attrs={"step": "0.01"}), "approximate_balance": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company, financial_status=Truck.FINANCED)


class DriverForm(StyledModelForm):
    access_username = forms.CharField(label="Novo usuário de acesso", required=False, help_text="Preencha somente para criar uma conta individual para este motorista.")
    access_password = forms.CharField(label="Senha inicial", required=False, widget=forms.PasswordInput, help_text="Use pelo menos 8 caracteres; o motorista poderá trocar depois.")

    class Meta:
        model = Driver
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"admission_date": forms.DateInput(attrs={"type": "date"}), "monthly_fixed": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(fleet_profile__company=self.company, fleet_profile__role="DRIVER")

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get("access_username")
        password = cleaned.get("access_password")
        if username:
            if User.objects.filter(username=username).exists():
                self.add_error("access_username", "Este usuário já existe.")
            if not password:
                self.add_error("access_password", "Informe uma senha para a nova conta.")
            else:
                try:
                    validate_password(password)
                except ValidationError as error:
                    self.add_error("access_password", error)
        return cleaned


class ContractForm(StyledModelForm):
    class Meta:
        model = Contract
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"}), "contracted_value": forms.NumberInput(attrs={"step": "0.01"}), "value_per_km": forms.NumberInput(attrs={"step": "0.01"}), "value_per_trip": forms.NumberInput(attrs={"step": "0.01"})}


class TripStartForm(StyledModelForm):
    class Meta:
        model = Trip
        fields = ["truck", "contract", "origin", "destination", "start_odometer", "notes"]
        widgets = {"start_odometer": forms.NumberInput(attrs={"step": "0.1", "placeholder": "Ex.: 125430.0"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company, status=Truck.OPERATING)
        self.fields["contract"].queryset = Contract.objects.filter(company=self.company, status=Contract.ACTIVE)


class TripPlanForm(StyledModelForm):
    class Meta:
        model = Trip
        fields = ["truck", "driver", "contract", "origin", "destination", "planned_start_at", "planned_end_at", "cargo_description", "cargo_weight", "delivery_reference", "start_odometer", "notes"]
        widgets = {"planned_start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "planned_end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "cargo_weight": forms.NumberInput(attrs={"step": "0.01", "min": 0}), "start_odometer": forms.NumberInput(attrs={"step": "0.1", "placeholder": "Quilometragem prevista"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.instance.company = self.company
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company, status=Truck.OPERATING)
        self.fields["driver"].queryset = Driver.objects.filter(company=self.company, status=Driver.ACTIVE)
        self.fields["contract"].queryset = Contract.objects.filter(company=self.company, status=Contract.ACTIVE)


class TripStartPlannedForm(forms.Form):
    start_odometer = forms.DecimalField(label="Quilometragem inicial", min_value=0, decimal_places=1, max_digits=12, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}))
    notes = forms.CharField(label="Observação", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))


class TripFinishForm(forms.Form):
    end_odometer = forms.DecimalField(label="Quilometragem final", min_value=0, decimal_places=1, max_digits=12, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}))
    delivery_proof = forms.FileField(label="Comprovante de entrega", required=False, help_text="Foto ou arquivo da entrega, se disponível.", widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*,.pdf"}))
    notes = forms.CharField(label="Observação", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))


class StopForm(StyledModelForm):
    class Meta:
        model = Stop
        fields = ["location", "started_at", "ended_at", "reason", "odometer", "notes"]
        widgets = {"started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), "odometer": forms.NumberInput(attrs={"step": "0.1"})}

    def __init__(self, *args, trip=None, **kwargs):
        self.trip = trip
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("started_at", timezone.localtime().replace(second=0, microsecond=0))

    def clean(self):
        cleaned = super().clean()
        started_at, ended_at = cleaned.get("started_at"), cleaned.get("ended_at")
        trip_start = self.trip.started_at.replace(second=0, microsecond=0) if self.trip and self.trip.started_at else None
        if trip_start and started_at and started_at < trip_start:
            self.add_error("started_at", "A pausa não pode começar antes do início da viagem.")
        if trip_start and ended_at and ended_at < trip_start:
            self.add_error("ended_at", "A pausa não pode terminar antes do início da viagem.")
        return cleaned


class FuelingForm(StyledModelForm):
    class Meta:
        model = Fueling
        exclude = ["company", "driver", "price_per_liter", "km_per_liter", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"fueled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), "odometer": forms.NumberInput(attrs={"step": "0.1"}), "liters": forms.NumberInput(attrs={"step": "0.01"}), "total_amount": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)
        self.fields["trip"].queryset = Trip.objects.filter(company=self.company)
        if self.user and hasattr(self.user, "driver_record"):
            self.fields["trip"].queryset = self.fields["trip"].queryset.filter(driver=self.user.driver_record)
        if not self.is_bound:
            self.initial.setdefault("fueled_at", timezone.localtime().replace(second=0, microsecond=0))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("trip") and cleaned.get("truck") and cleaned["trip"].truck_id != cleaned["truck"].id:
            raise ValidationError("O trecho selecionado pertence a outro caminhão.")
        trip, fueled_at = cleaned.get("trip"), cleaned.get("fueled_at")
        trip_start = trip.started_at.replace(second=0, microsecond=0) if trip and trip.started_at else None
        if trip_start and fueled_at and fueled_at < trip_start:
            self.add_error("fueled_at", "O abastecimento não pode ser anterior ao início da viagem.")
        if trip and fueled_at and trip.ended_at and fueled_at > trip.ended_at:
            self.add_error("fueled_at", "O abastecimento não pode ser posterior ao fim da viagem.")
        return cleaned


class VehicleChecklistForm(StyledModelForm):
    class Meta:
        model = VehicleChecklist
        fields = ["truck", "trip", "tires_ok", "lights_ok", "oil_ok", "brakes_ok", "documents_ok", "notes"]

    def __init__(self, *args, driver=None, **kwargs):
        self.driver = driver
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company, status=Truck.OPERATING)
        self.fields["trip"].queryset = Trip.objects.filter(company=self.company, driver=driver, status=Trip.IN_PROGRESS)

    def clean(self):
        cleaned = super().clean()
        trip, truck = cleaned.get("trip"), cleaned.get("truck")
        if trip and truck and trip.truck_id != truck.id:
            raise ValidationError("O trecho selecionado pertence a outro caminhão.")
        return cleaned


class MaintenanceForm(StyledModelForm):
    class Meta:
        model = Maintenance
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "next_date": forms.DateInput(attrs={"type": "date"}), "odometer": forms.NumberInput(attrs={"step": "0.1"}), "next_odometer": forms.NumberInput(attrs={"step": "0.1"}), "amount": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)


class MaintenancePlanForm(StyledModelForm):
    class Meta:
        model = MaintenancePlan
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"next_due_date": forms.DateInput(attrs={"type": "date"}), "next_due_odometer": forms.NumberInput(attrs={"step": "0.1"}), "interval_km": forms.NumberInput(attrs={"step": "0.1"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.instance.company = self.company
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)


class TireExpenseForm(StyledModelForm):
    class Meta:
        model = TireExpense
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "amount": forms.NumberInput(attrs={"step": "0.01"}), "odometer": forms.NumberInput(attrs={"step": "0.1"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)


class CashEntryForm(StyledModelForm):
    class Meta:
        model = CashEntry
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by", "paid_at"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}), "amount": forms.NumberInput(attrs={"step": "0.01", "min": 0})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.instance.company = self.company
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)
        self.fields["contract"].queryset = Contract.objects.filter(company=self.company)


class ProductionForm(StyledModelForm):
    class Meta:
        model = Production
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"competence": forms.DateInput(attrs={"type": "date"}), "realized_value": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("contract", "trip", "truck", "driver"):
            self.fields[field].queryset = self.fields[field].queryset.filter(company=self.company)


class RemunerationRuleForm(StyledModelForm):
    class Meta:
        model = RemunerationRule
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"effective_from": forms.DateInput(attrs={"type": "date"}), "effective_until": forms.DateInput(attrs={"type": "date"}), "commission_percent": forms.NumberInput(attrs={"step": "0.01"}), "bonus_km_limit": forms.NumberInput(attrs={"step": "0.1"}), "bonus_amount": forms.NumberInput(attrs={"step": "0.01"}), "bonus_percent": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("driver", "contract"):
            self.fields[field].queryset = self.fields[field].queryset.filter(company=self.company)


class FixedCostForm(StyledModelForm):
    class Meta:
        model = FixedCost
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"valid_from": forms.DateInput(attrs={"type": "date"}), "valid_until": forms.DateInput(attrs={"type": "date"}), "monthly_amount": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)


class OccurrenceForm(StyledModelForm):
    class Meta:
        model = Occurrence
        exclude = ["company", "driver", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        self.driver = kwargs.pop("driver", None)
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)
        self.fields["trip"].queryset = Trip.objects.filter(company=self.company)
