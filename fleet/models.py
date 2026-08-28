from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Company(models.Model):
    name = models.CharField("nome", max_length=160)
    code = models.SlugField("código", max_length=50, unique=True)
    active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    MANAGER = "MANAGER"
    DRIVER = "DRIVER"
    ROLE_CHOICES = [(MANAGER, "Gestor"), (DRIVER, "Motorista")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="fleet_profile")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="user_profiles")
    role = models.CharField("perfil", max_length=12, choices=ROLE_CHOICES, default=DRIVER)
    phone = models.CharField("telefone", max_length=30, blank=True)

    class Meta:
        verbose_name = "perfil de usuário"
        verbose_name_plural = "perfis de usuários"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} · {self.get_role_display()}"


class CompanyModel(models.Model):
    """Common audit fields for the main records are kept explicitly per model.

    This abstract base also makes it straightforward to add tenant-aware common
    behaviour without hiding the company foreign key from Django/admin.
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="%(class)s_created", null=True, blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="%(class)s_updated", null=True, blank=True)

    class Meta:
        abstract = True


class Truck(CompanyModel):
    FUEL_DIESEL = "DIESEL"
    FUEL_GASOLINE = "GASOLINE"
    FUEL_ETHANOL = "ETHANOL"
    FUEL_GNV = "GNV"
    FUEL_CHOICES = [(FUEL_DIESEL, "Diesel"), (FUEL_GASOLINE, "Gasolina"), (FUEL_ETHANOL, "Etanol"), (FUEL_GNV, "GNV")]
    OPERATING = "OPERATING"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"
    STATUS_CHOICES = [(OPERATING, "Em operação"), (MAINTENANCE, "Em manutenção"), (INACTIVE, "Inativo")]
    FINANCED = "FINANCED"
    PAID = "PAID"
    FINANCIAL_CHOICES = [(FINANCED, "Financiado"), (PAID, "Quitado")]

    identification = models.CharField("identificação", max_length=40)
    simulated_plate = models.CharField("placa simulada", max_length=20)
    model = models.CharField("modelo", max_length=80)
    brand = models.CharField("marca", max_length=80)
    year = models.PositiveIntegerField("ano", null=True, blank=True)
    fuel_type = models.CharField("combustível", max_length=12, choices=FUEL_CHOICES, default=FUEL_DIESEL)
    tank_capacity = models.DecimalField("capacidade do tanque (L)", max_digits=9, decimal_places=2, default=0)
    current_odometer = models.DecimalField("quilometragem atual", max_digits=12, decimal_places=1, default=0)
    status = models.CharField("status", max_length=15, choices=STATUS_CHOICES, default=OPERATING)
    financial_status = models.CharField("situação financeira", max_length=10, choices=FINANCIAL_CHOICES, default=PAID)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["identification"]
        constraints = [models.UniqueConstraint(fields=["company", "identification"], name="unique_truck_identification_per_company")]
        verbose_name = "caminhão"
        verbose_name_plural = "caminhões"

    def __str__(self):
        return f"{self.identification} · {self.model}"


class Financing(CompanyModel):
    truck = models.OneToOneField(Truck, on_delete=models.CASCADE, related_name="financing")
    monthly_payment = models.DecimalField("parcela mensal", max_digits=12, decimal_places=2, default=0)
    financial_institution = models.CharField("instituição financeira", max_length=120, blank=True)
    start_date = models.DateField("data inicial", null=True, blank=True)
    expected_end_date = models.DateField("data final prevista", null=True, blank=True)
    installments = models.PositiveIntegerField("quantidade de parcelas", default=0)
    installments_paid = models.PositiveIntegerField("parcelas pagas", default=0)
    approximate_balance = models.DecimalField("saldo aproximado", max_digits=14, decimal_places=2, default=0)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["truck"]
        verbose_name = "financiamento"
        verbose_name_plural = "financiamentos"

    def __str__(self):
        return f"Financiamento · {self.truck.identification}"


class Driver(CompanyModel):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    STATUS_CHOICES = [(ACTIVE, "Ativo"), (INACTIVE, "Inativo")]
    name = models.CharField("nome", max_length=160)
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="driver_record", null=True, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    status = models.CharField("status", max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    admission_date = models.DateField("data de admissão", null=True, blank=True)
    monthly_fixed = models.DecimalField("valor fixo mensal", max_digits=12, decimal_places=2, default=0)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="unique_driver_name_per_company")]
        verbose_name = "motorista"
        verbose_name_plural = "motoristas"

    def __str__(self):
        return self.name


class Contract(CompanyModel):
    MANUAL = "MANUAL"
    PER_KM = "PER_KM"
    PER_TRIP = "PER_TRIP"
    MONTHLY = "MONTHLY"
    PRODUCTION_CHOICES = [(MANUAL, "Valor manual"), (PER_KM, "Valor por quilômetro"), (PER_TRIP, "Valor por viagem"), (MONTHLY, "Valor fixo mensal")]
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    DRAFT = "DRAFT"
    STATUS_CHOICES = [(ACTIVE, "Ativo"), (CLOSED, "Encerrado"), (DRAFT, "Rascunho")]
    client_name = models.CharField("nome do cliente", max_length=160)
    code = models.CharField("código do contrato", max_length=50)
    description = models.TextField("descrição", blank=True)
    contracted_value = models.DecimalField("valor contratado", max_digits=14, decimal_places=2, default=0)
    start_date = models.DateField("data inicial")
    end_date = models.DateField("data final", null=True, blank=True)
    status = models.CharField("status", max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    production_type = models.CharField("tipo de produção", max_length=10, choices=PRODUCTION_CHOICES, default=MANUAL)
    value_per_km = models.DecimalField("valor por km", max_digits=10, decimal_places=2, default=0)
    value_per_trip = models.DecimalField("valor por viagem", max_digits=12, decimal_places=2, default=0)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-start_date", "client_name"]
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="unique_contract_code_per_company")]
        verbose_name = "contrato"
        verbose_name_plural = "contratos"

    def __str__(self):
        return f"{self.code} · {self.client_name}"


class Trip(CompanyModel):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"
    REOPENED = "REOPENED"
    STATUS_CHOICES = [(PLANNED, "Planejado"), (IN_PROGRESS, "Em andamento"), (FINISHED, "Finalizado"), (CANCELLED, "Cancelado"), (REOPENED, "Reaberto para correção")]
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="trips")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="trips")
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="trips")
    origin = models.CharField("origem", max_length=120)
    destination = models.CharField("destino", max_length=120)
    start_odometer = models.DecimalField("quilometragem inicial", max_digits=12, decimal_places=1)
    end_odometer = models.DecimalField("quilometragem final", max_digits=12, decimal_places=1, null=True, blank=True)
    started_at = models.DateTimeField("início", null=True, blank=True)
    ended_at = models.DateTimeField("fim", null=True, blank=True)
    distance_km = models.DecimalField("quilômetros rodados", max_digits=12, decimal_places=1, default=0)
    duration = models.DurationField("duração", null=True, blank=True)
    status = models.CharField("status", max_length=15, choices=STATUS_CHOICES, default=PLANNED)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        indexes = [models.Index(fields=["company", "status"]), models.Index(fields=["company", "started_at"])]
        verbose_name = "trecho"
        verbose_name_plural = "trechos"

    def clean(self):
        errors = {}
        if self.truck_id and self.driver_id:
            if self.truck.company_id != self.company_id or self.driver.company_id != self.company_id or self.contract.company_id != self.company_id:
                raise ValidationError("Caminhão, motorista, contrato e trecho devem pertencer à mesma empresa.")
        if self.end_odometer is not None and self.end_odometer < self.start_odometer:
            errors["end_odometer"] = "A quilometragem final não pode ser menor que a inicial."
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            errors["ended_at"] = "A data final não pode ser anterior à data inicial."
        if errors:
            raise ValidationError(errors)

    def start(self):
        if Trip.objects.filter(truck=self.truck, status=Trip.IN_PROGRESS).exclude(pk=self.pk).exists():
            raise ValidationError("Este caminhão já possui um trecho em andamento.")
        if Trip.objects.filter(driver=self.driver, status=Trip.IN_PROGRESS).exclude(pk=self.pk).exists():
            raise ValidationError("Este motorista já possui um trecho em andamento.")
        if self.start_odometer < self.truck.current_odometer:
            raise ValidationError("A quilometragem inicial não pode ser menor que o último registro do caminhão.")
        self.started_at = timezone.now()
        self.status = self.IN_PROGRESS
        self.distance_km = Decimal("0")

    def finish(self, end_odometer, notes=""):
        end_odometer = Decimal(str(end_odometer))
        if end_odometer < self.start_odometer:
            raise ValidationError("A quilometragem final não pode ser menor que a inicial.")
        if end_odometer < self.truck.current_odometer:
            raise ValidationError("A quilometragem final não pode ser menor que o último registro do caminhão.")
        if not self.started_at:
            raise ValidationError("O trecho ainda não foi iniciado.")
        self.end_odometer = end_odometer
        self.ended_at = timezone.now()
        self.distance_km = end_odometer - self.start_odometer
        self.duration = self.ended_at - self.started_at
        self.notes = notes or self.notes
        self.status = self.FINISHED
        Truck.objects.filter(pk=self.truck_id).update(current_odometer=end_odometer)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = Trip.objects.filter(pk=self.pk).first()
            if previous and previous.status == self.FINISHED and self.status == self.FINISHED:
                locked_fields = ("truck_id", "driver_id", "contract_id", "origin", "destination", "start_odometer", "end_odometer", "started_at", "ended_at", "distance_km", "duration", "notes")
                if any(getattr(previous, field) != getattr(self, field) for field in locked_fields):
                    raise ValidationError("Trecho finalizado está bloqueado. Reabra-o para correção antes de editar.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.origin} → {self.destination} · {self.truck.identification}"


class Stop(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    location = models.CharField("local", max_length=160)
    started_at = models.DateTimeField("início")
    ended_at = models.DateTimeField("fim", null=True, blank=True)
    reason = models.CharField("motivo", max_length=160)
    odometer = models.DecimalField("quilometragem", max_digits=12, decimal_places=1, null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["started_at"]
        verbose_name = "parada"
        verbose_name_plural = "paradas"

    def clean(self):
        if self.ended_at and self.ended_at < self.started_at:
            raise ValidationError("O fim da parada não pode ser anterior ao início.")

    def __str__(self):
        return f"{self.location} · {self.reason}"


class Fueling(CompanyModel):
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="fuelings")
    trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, related_name="fuelings", null=True, blank=True)
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, related_name="fuelings", null=True, blank=True)
    fueled_at = models.DateTimeField("data e hora", default=timezone.now)
    city = models.CharField("cidade", max_length=100)
    state = models.CharField("estado", max_length=2)
    station = models.CharField("posto", max_length=160)
    fuel_type = models.CharField("combustível", max_length=12, choices=Truck.FUEL_CHOICES)
    odometer = models.DecimalField("quilometragem atual", max_digits=12, decimal_places=1)
    liters = models.DecimalField("litros", max_digits=10, decimal_places=2)
    total_amount = models.DecimalField("valor total", max_digits=12, decimal_places=2)
    tank_full = models.BooleanField("tanque completado", default=False)
    price_per_liter = models.DecimalField("preço por litro", max_digits=10, decimal_places=3, default=0)
    km_per_liter = models.DecimalField("km por litro", max_digits=8, decimal_places=2, null=True, blank=True)
    receipt = models.FileField("comprovante", upload_to="fuelings/%Y/%m/", null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["-fueled_at"]
        indexes = [models.Index(fields=["company", "fueled_at"])]
        verbose_name = "abastecimento"
        verbose_name_plural = "abastecimentos"

    def clean(self):
        errors = {}
        if self.liters is None or self.liters <= 0:
            errors["liters"] = "A quantidade de litros deve ser maior que zero."
        if self.total_amount is not None and self.total_amount < 0:
            errors["total_amount"] = "O valor não pode ser negativo."
        if self.odometer is not None and self.truck_id and self.odometer < self.truck.current_odometer:
            errors["odometer"] = "A quilometragem não pode ser menor que o último registro do caminhão."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.liters and self.liters > 0:
            self.price_per_liter = self.total_amount / self.liters
        self.km_per_liter = None
        if self.tank_full and self.truck_id:
            previous = Fueling.objects.filter(truck_id=self.truck_id, tank_full=True).exclude(pk=self.pk).filter(fueled_at__lt=self.fueled_at).order_by("-fueled_at").first()
            if previous and self.odometer > previous.odometer:
                self.km_per_liter = (self.odometer - previous.odometer) / self.liters
        super().save(*args, **kwargs)
        if self.truck_id and self.odometer > self.truck.current_odometer:
            Truck.objects.filter(pk=self.truck_id).update(current_odometer=self.odometer)

    def __str__(self):
        return f"{self.truck.identification} · {self.liters} L"


class Maintenance(CompanyModel):
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    TIRES = "TIRES"
    OIL = "OIL"
    BRAKES = "BRAKES"
    ENGINE = "ENGINE"
    ELECTRIC = "ELECTRIC"
    OTHER = "OTHER"
    TYPE_CHOICES = [(PREVENTIVE, "Preventiva"), (CORRECTIVE, "Corretiva"), (TIRES, "Pneus"), (OIL, "Óleo"), (BRAKES, "Freios"), (ENGINE, "Motor"), (ELECTRIC, "Elétrica"), (OTHER, "Outros")]
    OPEN = "OPEN"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    STATUS_CHOICES = [(OPEN, "Em aberto"), (DONE, "Concluída"), (CANCELLED, "Cancelada")]
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="maintenances")
    maintenance_type = models.CharField("tipo", max_length=12, choices=TYPE_CHOICES)
    date = models.DateField("data")
    odometer = models.DecimalField("quilometragem", max_digits=12, decimal_places=1, default=0)
    description = models.CharField("descrição", max_length=240)
    workshop = models.CharField("oficina", max_length=160, blank=True)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2, default=0)
    downtime_days = models.PositiveIntegerField("tempo parado (dias)", default=0)
    next_date = models.DateField("próxima data", null=True, blank=True)
    next_odometer = models.DecimalField("próxima quilometragem", max_digits=12, decimal_places=1, null=True, blank=True)
    status = models.CharField("status", max_length=10, choices=STATUS_CHOICES, default=DONE)
    notes = models.TextField("observação", blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "manutenção"
        verbose_name_plural = "manutenções"

    def __str__(self):
        return f"{self.truck.identification} · {self.get_maintenance_type_display()}"


class TireExpense(CompanyModel):
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="tire_expenses")
    date = models.DateField("data")
    quantity = models.PositiveIntegerField("quantidade")
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    odometer = models.DecimalField("quilometragem", max_digits=12, decimal_places=1, default=0)
    supplier = models.CharField("fornecedor", max_length=160, blank=True)
    notes = models.TextField("observação", blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "despesa com pneu"
        verbose_name_plural = "despesas com pneus"

    def __str__(self):
        return f"Pneus · {self.truck.identification}"


class FixedCost(CompanyModel):
    INSURANCE = "INSURANCE"
    TAX = "TAX"
    OTHER = "OTHER"
    CATEGORY_CHOICES = [(INSURANCE, "Seguro"), (TAX, "IPVA"), (OTHER, "Outros custos fixos")]
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="fixed_costs", null=True, blank=True)
    category = models.CharField("categoria", max_length=10, choices=CATEGORY_CHOICES)
    description = models.CharField("descrição", max_length=180)
    monthly_amount = models.DecimalField("valor mensal", max_digits=12, decimal_places=2)
    valid_from = models.DateField("vigência inicial")
    valid_until = models.DateField("vigência final", null=True, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["-valid_from"]
        verbose_name = "custo fixo"
        verbose_name_plural = "custos fixos"

    def __str__(self):
        return f"{self.get_category_display()} · {self.description}"


class Production(CompanyModel):
    OPEN = "OPEN"
    CONFERRED = "CONFERRED"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    STATUS_CHOICES = [(OPEN, "Em aberto"), (CONFERRED, "Conferida"), (APPROVED, "Aprovada"), (CANCELLED, "Cancelada")]
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="productions")
    competence = models.DateField("data/competência")
    trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, related_name="productions", null=True, blank=True)
    truck = models.ForeignKey(Truck, on_delete=models.SET_NULL, related_name="productions", null=True, blank=True)
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, related_name="productions", null=True, blank=True)
    realized_value = models.DecimalField("valor realizado", max_digits=14, decimal_places=2)
    status = models.CharField("status", max_length=12, choices=STATUS_CHOICES, default=OPEN)
    notes = models.TextField("observação", blank=True)

    class Meta:
        ordering = ["-competence"]
        verbose_name = "produção financeira"
        verbose_name_plural = "produções financeiras"

    def clean(self):
        if self.trip_id:
            if self.trip.company_id != self.company_id or self.trip.contract_id != self.contract_id:
                raise ValidationError("O trecho e o contrato precisam pertencer à mesma empresa e produção.")
            if self.truck_id and self.truck_id != self.trip.truck_id:
                raise ValidationError("O caminhão deve ser o caminhão do trecho.")
            if self.driver_id and self.driver_id != self.trip.driver_id:
                raise ValidationError("O motorista deve ser o motorista do trecho.")

    def __str__(self):
        return f"{self.contract.code} · R$ {self.realized_value}"


class RemunerationRule(CompanyModel):
    REALIZED = "REALIZED"
    DISTANCE = "DISTANCE"
    TRIPS = "TRIPS"
    BASE_CHOICES = [(REALIZED, "Valor realizado"), (DISTANCE, "Quilometragem"), (TRIPS, "Quantidade de viagens")]
    NO_BONUS = "NONE"
    KM_BONUS = "KM"
    TRIP_BONUS = "TRIPS"
    FIXED_BONUS = "FIXED"
    PERCENT_BONUS = "PERCENT"
    BONUS_CHOICES = [(NO_BONUS, "Sem bônus"), (KM_BONUS, "Por quilometragem"), (TRIP_BONUS, "Por viagens"), (FIXED_BONUS, "Bônus fixo"), (PERCENT_BONUS, "Bônus percentual")]
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="remuneration_rules", null=True, blank=True)
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="remuneration_rules", null=True, blank=True)
    effective_from = models.DateField("vigência inicial")
    effective_until = models.DateField("vigência final", null=True, blank=True)
    priority = models.PositiveIntegerField("prioridade", default=0)
    commission_percent = models.DecimalField("percentual de comissão", max_digits=6, decimal_places=2, default=0)
    commission_base = models.CharField("base da comissão", max_length=10, choices=BASE_CHOICES, default=REALIZED)
    fixed_monthly = models.DecimalField("valor fixo mensal", max_digits=12, decimal_places=2, default=0)
    bonus_type = models.CharField("tipo de bônus", max_length=8, choices=BONUS_CHOICES, default=NO_BONUS)
    bonus_km_limit = models.DecimalField("limite de quilômetros", max_digits=12, decimal_places=1, null=True, blank=True)
    bonus_trip_limit = models.PositiveIntegerField("limite de viagens", null=True, blank=True)
    bonus_amount = models.DecimalField("valor do bônus", max_digits=12, decimal_places=2, default=0)
    bonus_percent = models.DecimalField("percentual do bônus", max_digits=6, decimal_places=2, default=0)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["-priority", "-effective_from"]
        verbose_name = "regra de remuneração"
        verbose_name_plural = "regras de remuneração"

    def __str__(self):
        scope = self.driver.name if self.driver else "empresa"
        return f"{scope} · {self.effective_from}"


class Remuneration(CompanyModel):
    CALCULATING = "CALCULATING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PAID = "PAID"
    STATUS_CHOICES = [(CALCULATING, "Em cálculo"), (REVIEW, "Em conferência"), (APPROVED, "Aprovada"), (PAID, "Paga")]
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="remunerations")
    competence = models.DateField("competência")
    fixed_amount = models.DecimalField("valor fixo", max_digits=12, decimal_places=2, default=0)
    commission_base_value = models.DecimalField("base da comissão", max_digits=14, decimal_places=2, default=0)
    commission_percent = models.DecimalField("percentual utilizado", max_digits=6, decimal_places=2, default=0)
    commission_amount = models.DecimalField("comissão", max_digits=14, decimal_places=2, default=0)
    km_bonus = models.DecimalField("bônus por quilometragem", max_digits=12, decimal_places=2, default=0)
    trips_bonus = models.DecimalField("bônus por viagens", max_digits=12, decimal_places=2, default=0)
    other_bonus = models.DecimalField("outros bônus", max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField("total estimado", max_digits=14, decimal_places=2, default=0)
    status = models.CharField("status", max_length=12, choices=STATUS_CHOICES, default=CALCULATING)
    calculation_notes = models.TextField("memória de cálculo", blank=True)

    class Meta:
        ordering = ["-competence", "driver"]
        constraints = [models.UniqueConstraint(fields=["driver", "competence"], name="unique_remuneration_driver_competence")]
        verbose_name = "remuneração"
        verbose_name_plural = "remunerações"

    def __str__(self):
        return f"{self.driver.name} · {self.competence:%m/%Y}"


class Occurrence(CompanyModel):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    STATUS_CHOICES = [(OPEN, "Aberta"), (RESOLVED, "Resolvida")]
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="occurrences")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="occurrences")
    trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, related_name="occurrences", null=True, blank=True)
    occurred_at = models.DateTimeField("data e hora", default=timezone.now)
    title = models.CharField("título", max_length=160)
    description = models.TextField("descrição")
    status = models.CharField("status", max_length=10, choices=STATUS_CHOICES, default=OPEN)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REOPEN = "REOPEN"
    ACTION_CHOICES = [(CREATE, "Criação"), (UPDATE, "Alteração"), (REOPEN, "Reabertura")]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="audit_logs")
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="fleet_audits")
    action = models.CharField("ação", max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField("modelo", max_length=80)
    object_id = models.CharField("registro", max_length=80)
    reason = models.TextField("motivo", blank=True)
    before_data = models.JSONField("valor anterior", default=dict, blank=True)
    after_data = models.JSONField("novo valor", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "auditoria"
        verbose_name_plural = "auditorias"

    def __str__(self):
        return f"{self.get_action_display()} · {self.model_name} #{self.object_id}"
