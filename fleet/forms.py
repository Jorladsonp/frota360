from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Contract, Driver, Financing, FixedCost, Fueling, Maintenance, Occurrence, Production, RemunerationRule, Stop, TireExpense, Trip, Truck


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


class TripFinishForm(forms.Form):
    end_odometer = forms.DecimalField(label="Quilometragem final", min_value=0, decimal_places=1, max_digits=12, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}))
    notes = forms.CharField(label="Observação", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))


class StopForm(StyledModelForm):
    class Meta:
        model = Stop
        fields = ["location", "started_at", "ended_at", "reason", "odometer", "notes"]
        widgets = {"started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "odometer": forms.NumberInput(attrs={"step": "0.1"})}


class FuelingForm(StyledModelForm):
    class Meta:
        model = Fueling
        exclude = ["company", "driver", "price_per_liter", "km_per_liter", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"fueled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "odometer": forms.NumberInput(attrs={"step": "0.1"}), "liters": forms.NumberInput(attrs={"step": "0.01"}), "total_amount": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)
        self.fields["trip"].queryset = Trip.objects.filter(company=self.company)
        if self.user and hasattr(self.user, "driver_record"):
            self.fields["trip"].queryset = self.fields["trip"].queryset.filter(driver=self.user.driver_record)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("trip") and cleaned.get("truck") and cleaned["trip"].truck_id != cleaned["truck"].id:
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


class TireExpenseForm(StyledModelForm):
    class Meta:
        model = TireExpense
        exclude = ["company", "created_at", "updated_at", "created_by", "updated_by"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "amount": forms.NumberInput(attrs={"step": "0.01"}), "odometer": forms.NumberInput(attrs={"step": "0.1"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["truck"].queryset = Truck.objects.filter(company=self.company)


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
