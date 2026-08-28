"""
URL configuration for hello_world project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles import views as static_views

from fleet import views as fleet_views

urlpatterns = [
    path("", fleet_views.home, name="home"),
    path("login/", fleet_views.login_view, name="login"),
    path("logout/", fleet_views.logout_view, name="logout"),
    path("gestor/", fleet_views.dashboard, name="dashboard"),
    path("motorista/", fleet_views.driver_dashboard, name="driver_dashboard"),
    path("gestor/caminhoes/", fleet_views.truck_list, name="truck_list"),
    path("gestor/caminhoes/novo/", fleet_views.truck_create, name="truck_create"),
    path("gestor/caminhoes/<int:pk>/editar/", fleet_views.truck_update, name="truck_update"),
    path("gestor/financiamentos/", fleet_views.financing_list, name="financing_list"),
    path("gestor/financiamentos/novo/", fleet_views.financing_create, name="financing_create"),
    path("gestor/financiamentos/<int:pk>/editar/", fleet_views.financing_update, name="financing_update"),
    path("gestor/motoristas/", fleet_views.driver_list, name="driver_list"),
    path("gestor/motoristas/novo/", fleet_views.driver_create, name="driver_create"),
    path("gestor/motoristas/<int:pk>/editar/", fleet_views.driver_update, name="driver_update"),
    path("gestor/contratos/", fleet_views.contract_list, name="contract_list"),
    path("gestor/contratos/novo/", fleet_views.contract_create, name="contract_create"),
    path("gestor/contratos/<int:pk>/editar/", fleet_views.contract_update, name="contract_update"),
    path("gestor/manutencoes/", fleet_views.maintenance_list, name="maintenance_list"),
    path("gestor/manutencoes/nova/", fleet_views.maintenance_create, name="maintenance_create"),
    path("gestor/pneus/novo/", fleet_views.tire_create, name="tire_create"),
    path("gestor/producoes/", fleet_views.production_list, name="production_list"),
    path("gestor/producoes/nova/", fleet_views.production_create, name="production_create"),
    path("gestor/regras/", fleet_views.rule_list, name="rule_list"),
    path("gestor/regras/nova/", fleet_views.rule_create, name="rule_create"),
    path("gestor/custos-fixos/", fleet_views.fixed_cost_list, name="fixed_cost_list"),
    path("gestor/custos-fixos/novo/", fleet_views.fixed_cost_create, name="fixed_cost_create"),
    path("trechos/", fleet_views.trip_list, name="trip_list"),
    path("trechos/iniciar/", fleet_views.trip_start, name="trip_start"),
    path("trechos/<int:pk>/", fleet_views.trip_detail, name="trip_detail"),
    path("trechos/<int:pk>/finalizar/", fleet_views.trip_finish, name="trip_finish"),
    path("trechos/<int:pk>/parada/", fleet_views.stop_create, name="stop_create"),
    path("gestor/trechos/<int:pk>/reabrir/", fleet_views.reopen_trip, name="reopen_trip"),
    path("gestor/trechos/<int:pk>/corrigir/", fleet_views.trip_update, name="trip_update"),
    path("abastecimentos/", fleet_views.fueling_list, name="fueling_list"),
    path("abastecimentos/novo/", fleet_views.fueling_create, name="fueling_create"),
    path("ocorrencias/nova/", fleet_views.occurrence_create, name="occurrence_create"),
    path("remuneracao/", fleet_views.remuneration_view, name="remuneration_view"),
    path("motorista/remuneracao/", fleet_views.driver_remuneration_view, name="driver_remuneration_view"),
    path("relatorios/<slug:report_name>/", fleet_views.report_view, name="report_view"),
    path("relatorios/<slug:report_name>/csv/", fleet_views.report_csv, name="report_csv"),
    path("admin/", admin.site.urls),
    path("__reload__/", include("django_browser_reload.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# The Codespaces starter environment may inject DEBUG=release. Keep local
# development assets available while production deployments should use
# collectstatic plus a proper static server.
urlpatterns += [re_path(r"^static/(?P<path>.*)$", static_views.serve, {"insecure": True})]
