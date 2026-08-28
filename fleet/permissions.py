from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from .models import UserProfile


def profile_for(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return None
    return getattr(user, "fleet_profile", None)


def manager_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        profile = profile_for(request.user)
        if request.user.is_superuser or (profile and profile.role == UserProfile.MANAGER):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Você não tem permissão para acessar esta área.")
        return redirect("driver_dashboard")
    return wrapped


def driver_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        profile = profile_for(request.user)
        if profile and profile.role == UserProfile.DRIVER:
            return view_func(request, *args, **kwargs)
        if request.user.is_superuser or (profile and profile.role == UserProfile.MANAGER):
            return redirect("dashboard")
        messages.error(request, "Perfil de usuário não configurado.")
        return redirect("login")
    return wrapped


def company_for(user):
    profile = profile_for(user)
    return profile.company if profile else None
