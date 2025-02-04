from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from backup.models import BackupProfile
from backup_data.models import RouterBackup
from monitoring.models import RouterDownTime
from routerfleet_tools.models import WebadminSettings
from .models import Router, RouterGroup, RouterStatus, SSHKey, BackupSchedule
from .forms import RouterForm, RouterGroupForm, SSHKeyForm
from user_manager.models import UserAcl


@login_required
def view_router_list(request):
    router_list = Router.objects.all().order_by('name')
    last_router_status_change = RouterStatus.objects.filter(last_status_change__isnull=False).order_by('-last_status_change').first()
    if last_router_status_change:
        last_status_change_timestamp = last_router_status_change.last_status_change.isoformat()
    else:
        last_status_change_timestamp = 0

    default_backup_profile, _ = BackupProfile.objects.get_or_create(name='default')
    filter_group = None
    if request.GET.get('filter_group'):
        if request.GET.get('filter_group') == 'all':
            pass
        else:
            filter_group = get_object_or_404(RouterGroup, uuid=request.GET.get('filter_group'))
            router_list = router_list.filter(routergroup=filter_group)

    if not filter_group and request.GET.get('filter_group') != 'all':
        filter_group = RouterGroup.objects.filter(default_group=True).first()
    context = {
        'router_list': router_list,
        'page_title': 'Router List',
        'filter_group_list': RouterGroup.objects.all().order_by('name'),
        'filter_group': filter_group,
        'last_status_change_timestamp': last_status_change_timestamp,
    }
    return render(request, 'router_manager/router_list.html', context=context)


@login_required()
def view_router_availability(request):
    router = get_object_or_404(Router, uuid=request.GET.get('uuid'))
    data = {
        'router': router,
        'downtime_list': router.routerdowntime_set.all().order_by('-start_time'),
    }
    return render(request, 'router_manager/router_availability.html', context=data)


@login_required()
def view_router_details(request):
    router = get_object_or_404(Router, uuid=request.GET.get('uuid'))
    router_status, _ = RouterStatus.objects.get_or_create(router=router)
    router_backup_list = router.routerbackup_set.all().order_by('-created')
    downtime_last_week = router.routerdowntime_set.filter(start_time__gte=timezone.now() - timezone.timedelta(days=7)).aggregate(total=Sum('total_down_time'))['total']
    if downtime_last_week is None:
        downtime_last_week = 0
    total_last_week = 7 * 24 * 60 * 60  # total seconds in a week
    last_week_availability = round((total_last_week - downtime_last_week) / total_last_week * 100, 3)
    if downtime_last_week > 0 and last_week_availability == 100:
        last_week_availability = 99.999

    if router_status.backup_lock:
        if not router_backup_list.filter(success=False, error=False).exists():
            router_status.backup_lock = None
            router_status.save()
            messages.warning(request, 'Backup lock removed|Backup lock was removed as there are no active backup tasks')

    context = {
        'router': router,
        'router_status': router_status,
        'router_backup_list': router_backup_list,
        'page_title': 'Router Details',
        'offline_time_last_week': downtime_last_week,
        'last_week_availability': last_week_availability,

    }


    return render(request, 'router_manager/router_details.html', context=context)


@login_required()
def view_manage_router(request):
    if not UserAcl.objects.filter(user=request.user).filter(user_level__gte=30).exists():
        return render(request, 'access_denied.html', {'page_title': 'Access Denied'})
    webadmin_settings, _ = WebadminSettings.objects.get_or_create(name='webadmin_settings')

    if request.GET.get('uuid'):
        router = get_object_or_404(Router, uuid=request.GET.get('uuid'))
        if request.GET.get('action') == 'delete':
            if request.GET.get('confirmation') == 'delete':
                router.delete()
                messages.success(request, 'Router deleted successfully')
                webadmin_settings.router_config_last_updated = timezone.now()
                webadmin_settings.save()
                return redirect('router_list')
            else:
                messages.warning(request, 'Router not deleted|Invalid confirmation')
                return redirect('router_list')
    else:
        router = None

    form = RouterForm(request.POST or None, instance=router)
    if form.is_valid():
        form.save()
        messages.success(request, 'Router saved successfully|It may take a few minutes until monitoring starts for this router.')
        router_status, _ = RouterStatus.objects.get_or_create(router=form.instance)
        BackupSchedule.objects.filter(router=form.instance).delete()
        webadmin_settings.router_config_last_updated = timezone.now()
        webadmin_settings.save()
        return redirect('router_list')

    context = {
        'form': form,
        'page_title': 'Manage Router',
        'instance': router
    }
    return render(request, 'generic_form.html', context=context)


@login_required()
def view_router_group_list(request):
    context = {
        'router_group_list': RouterGroup.objects.all().order_by('name'),
        'page_title': 'Router Group List',
    }
    return render(request, 'router_manager/router_group_list.html', context=context)


@login_required()
def view_manage_router_group(request):
    if not UserAcl.objects.filter(user=request.user).filter(user_level__gte=40).exists():
        return render(request, 'access_denied.html', {'page_title': 'Access Denied'})
    if request.GET.get('uuid'):
        router_group = get_object_or_404(RouterGroup, uuid=request.GET.get('uuid'))
        if request.GET.get('action') == 'delete':
            if request.GET.get('confirmation') == 'delete':
                router_group.delete()
                messages.success(request, 'Router Group deleted successfully')
                return redirect('router_group_list')
            else:
                messages.warning(request, 'Router Group not deleted|Invalid confirmation')
                return redirect('router_group_list')
    else:
        router_group = None

    form = RouterGroupForm(request.POST or None, instance=router_group)
    if form.is_valid():
        form.save()
        messages.success(request, 'Router Group saved successfully')
        return redirect('router_group_list')

    context = {
        'form': form,
        'page_title': 'Manage Router Group',
        'instance': router_group
    }
    return render(request, 'generic_form.html', context=context)


@login_required()
def view_ssh_key_list(request):
    context = {
        'sshkey_list': SSHKey.objects.all().order_by('name'),
        'page_title': 'SSH Key List',
    }
    return render(request, 'router_manager/sshkey_list.html', context=context)


@login_required()
def view_manage_sshkey(request):
    if not UserAcl.objects.filter(user=request.user).filter(user_level__gte=40).exists():
        return render(request, 'access_denied.html', {'page_title': 'Access Denied'})
    if request.GET.get('uuid'):
        sshkey = get_object_or_404(SSHKey, uuid=request.GET.get('uuid'))
        if request.GET.get('action') == 'delete':
            if request.GET.get('confirmation') == 'delete':
                sshkey.delete()
                messages.success(request, 'SSH Key deleted successfully')
                return redirect('ssh_keys_list')
            else:
                messages.warning(request, 'SSH Key not deleted|Invalid confirmation')
                return redirect('ssh_keys_list')
    else:
        sshkey = None

    form = SSHKeyForm(request.POST or None, instance=sshkey)
    if form.is_valid():
        form.save()
        messages.success(request, 'SSH Key saved successfully')
        return redirect('ssh_keys_list')

    context = {
        'form': form,
        'page_title': 'Manage SSH Key',
        'instance': sshkey
    }
    return render(request, 'generic_form.html', context=context)


@login_required()
def view_create_instant_backup_task(request):
    if not UserAcl.objects.filter(user=request.user).filter(user_level__gte=20).exists():
        return render(request, 'access_denied.html', {'page_title': 'Access Denied'})
    router = get_object_or_404(Router, uuid=request.GET.get('uuid'))
    router_details_url = f'/router/details/?uuid={router.uuid}'
    if RouterBackup.objects.filter(router=router, success=False, error=False).exists():
        messages.warning(request, 'Backup task not created|Active router backup task already exists')
        return redirect(router_details_url)
    if router.routerstatus.backup_lock is not None:
        messages.warning(request, 'Backup task not created|Router backup is currently locked')
        return redirect(router_details_url)
    if not router.backup_profile:
        messages.warning(request, 'Backup task not created|Router has no backup profile')
        return redirect(router_details_url)

    router_backup = RouterBackup.objects.create(router=router, schedule_time=timezone.now(), schedule_type='instant')
    router.routerstatus.backup_lock = router_backup.schedule_time
    router.routerstatus.save()
    messages.success(request, 'Backup task created successfully')
    return redirect(router_details_url)

@login_required
def view_create_instant_backup_multiple_routers(request):
    if request.method == 'POST':
        if not UserAcl.objects.filter(user=request.user, user_level__gte=20).exists():
            return JsonResponse({'error': 'Permission denied.'}, status=403)

        uuids = request.POST.getlist('routers[]')  # Ajustat pentru a primi lista corect

        if not uuids:
            return JsonResponse({'error': 'No routers selected.'}, status=400)

        results = []
        for uuid in uuids:
            router = get_object_or_404(Router, uuid=uuid)
            
            if RouterBackup.objects.filter(router=router, success=False, error=False).exists():
                results.append({'router': router.name, 'status': 'active backup task exists'})
                continue

            if router.routerstatus.backup_lock:
                results.append({'router': router.name, 'status': 'backup locked'})
                continue

            if not router.backup_profile:
                results.append({'router': router.name, 'status': 'no backup profile'})
                continue

            router_backup = RouterBackup.objects.create(
                router=router,
                schedule_time=timezone.now(),
                schedule_type='instant'
            )

            router.routerstatus.backup_lock = router_backup.schedule_time
            router.routerstatus.save()

            results.append({'router': router.name, 'status': 'backup started'})

        return JsonResponse({'results': results})

    return JsonResponse({'error': 'Invalid request method.'}, status=405)
