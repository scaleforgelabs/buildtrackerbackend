from adrf.decorators import api_view
from asgiref.sync import sync_to_async
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema
from permissions import IsAdmin, IsSuperAdmin
from .models import ContentPost, SalesLead, LeadContact

User = get_user_model()


# ─── helpers ────────────────────────────────────────────────────────────────

def _user_row(u):
    return {
        'id': str(u.id),
        'email': u.email,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'platform_role': u.platform_role,
        'plan_type': u.plan_type,
        'status': u.status,
        'is_verified': u.is_verified,
        'created_at': u.created_at.isoformat(),
    }


# ─── stats ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Platform Stats")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_stats_view(request):
    @sync_to_async
    def _sync():
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        return Response({
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(status='active').count(),
            'new_users_this_week': User.objects.filter(created_at__gte=week_ago).count(),
            'admins': User.objects.filter(platform_role='admin').count(),
            'super_admins': User.objects.filter(platform_role='super_admin').count(),
        })
    return await _sync()


# ─── users ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="List Users")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_users_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Q
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        unverified_only = request.query_params.get('unverified', '').lower() == 'true'

        qs = User.objects.all()
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        if unverified_only:
            qs = qs.filter(is_verified=False)

        qs = qs.order_by('-created_at')
        total = qs.count()
        users = [_user_row(u) for u in qs[offset:offset + page_size]]
        return Response({'users': users, 'total': total, 'page': page, 'page_size': page_size})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update User Platform Role")
@api_view(['PATCH'])
@permission_classes([IsSuperAdmin])
async def admin_update_user_role_view(request, user_id):
    @sync_to_async
    def _sync():
        new_role = request.data.get('platform_role')
        valid_roles = ('user', 'admin', 'super_admin')
        if new_role not in valid_roles:
            return Response({'error': f'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        target.platform_role = new_role
        target.save(update_fields=['platform_role'])
        return Response({'id': str(target.id), 'email': target.email, 'platform_role': target.platform_role})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Delete User")
@api_view(['DELETE'])
@permission_classes([IsAdmin])
async def admin_delete_user_view(request, user_id):
    @sync_to_async
    def _sync():
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if str(target.id) == str(request.user.id):
            return Response({'error': 'Cannot delete your own account'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'admin' and target.is_verified:
            return Response({'error': 'Admins can only delete unverified users'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'super_admin' and target.platform_role == 'super_admin':
            return Response({'error': 'Cannot delete another super admin'}, status=status.HTTP_403_FORBIDDEN)
        email = target.email
        target.delete()
        return Response({'message': f'User {email} deleted'})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Suspend / Unsuspend User")
@api_view(['PATCH'])
@permission_classes([IsAdmin])
async def admin_suspend_user_view(request, user_id):
    @sync_to_async
    def _sync():
        action = request.data.get('action')
        if action not in ('suspend', 'unsuspend'):
            return Response({'error': 'action must be suspend or unsuspend'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if str(target.id) == str(request.user.id):
            return Response({'error': 'Cannot suspend your own account'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'admin' and target.platform_role in ('admin', 'super_admin'):
            return Response({'error': 'Admins cannot suspend other admins'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.platform_role == 'super_admin' and target.platform_role == 'super_admin':
            return Response({'error': 'Cannot suspend another super admin'}, status=status.HTTP_403_FORBIDDEN)
        target.status = 'inactive' if action == 'suspend' else 'active'
        target.save(update_fields=['status'])
        return Response({'id': str(target.id), 'email': target.email, 'status': target.status})
    return await _sync()


# ─── workspaces ──────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="List All Workspaces")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_workspaces_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count, Q
        from workspaces.models import Workspace
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        ws_type = request.query_params.get('type', '').strip()
        ws_status = request.query_params.get('status', '').strip()

        qs = Workspace.objects.select_related('owner').annotate(
            member_count=Count('members', distinct=True),
            task_count=Count('tasks', distinct=True),
        )
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(owner__email__icontains=search))
        if ws_type:
            qs = qs.filter(type=ws_type)
        if ws_status:
            qs = qs.filter(status=ws_status)

        total = qs.count()
        rows = []
        for ws in qs.order_by('-created_at')[offset:offset + page_size]:
            rows.append({
                'id': str(ws.id),
                'name': ws.name,
                'slug': ws.slug,
                'type': ws.type,
                'status': ws.status,
                'owner_email': ws.owner.email,
                'owner_name': f'{ws.owner.first_name} {ws.owner.last_name}'.strip(),
                'member_count': ws.member_count,
                'task_count': ws.task_count,
                'created_at': ws.created_at.isoformat(),
            })
        return Response({'workspaces': rows, 'total': total, 'page': page, 'page_size': page_size})
    return await _sync()


# ─── analytics ───────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Platform Analytics")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_analytics_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count
        from django.db.models.functions import TruncDate, TruncMonth
        from workspaces.models import Workspace, WorkspaceSettings

        now = timezone.now()
        days = int(request.query_params.get('days', 30))
        since = now - timedelta(days=days)

        # User growth (daily signups)
        user_growth = list(
            User.objects.filter(created_at__gte=since)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
            .values('date', 'count')
        )
        for row in user_growth:
            row['date'] = row['date'].isoformat()

        # Workspace growth (daily)
        ws_growth = list(
            Workspace.objects.filter(created_at__gte=since)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
            .values('date', 'count')
        )
        for row in ws_growth:
            row['date'] = row['date'].isoformat()

        # Workspace types breakdown
        ws_types = list(
            Workspace.objects.values('type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Most used modules (from WorkspaceSettings.enabled_modules JSON)
        module_counts = {}
        for s in WorkspaceSettings.objects.all():
            mods = s.enabled_modules or {}
            for mod, enabled in mods.items():
                if enabled:
                    module_counts[mod] = module_counts.get(mod, 0) + 1

        most_used_modules = sorted(
            [{'module': k, 'count': v} for k, v in module_counts.items()],
            key=lambda x: -x['count']
        )

        # Plan distribution
        plan_dist = list(
            User.objects.values('plan_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Top workspaces by task count
        from django.db.models import Count as C
        top_workspaces = list(
            Workspace.objects.annotate(task_count=C('tasks', distinct=True))
            .order_by('-task_count')[:10]
            .values('name', 'type', 'task_count', 'slug')
        )

        return Response({
            'user_growth': user_growth,
            'workspace_growth': ws_growth,
            'workspace_types': ws_types,
            'most_used_modules': most_used_modules,
            'plan_distribution': plan_dist,
            'top_workspaces': top_workspaces,
            'days': days,
        })
    return await _sync()


# ─── subscriptions ───────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Subscriptions Overview")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_subscriptions_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Count
        from subscriptions.models import Subscription, PaymentHistory

        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()

        # Plan breakdown
        plan_breakdown = list(
            Subscription.objects.values('plan_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        status_breakdown = list(
            Subscription.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Total paid (active non-free)
        paid_count = Subscription.objects.filter(status='active').exclude(plan_type='free').count()
        free_count = Subscription.objects.filter(plan_type='free').count()
        total = Subscription.objects.count()

        qs = Subscription.objects.select_related('organization')
        if search:
            qs = qs.filter(organization__name__icontains=search)

        rows = []
        for sub in qs.select_related('organization__owner').order_by('-created_at')[offset:offset + page_size]:
            rows.append({
                'id': str(sub.id),
                'organization': sub.organization.name if sub.organization else '—',
                'organization_id': str(sub.organization.id) if sub.organization else None,
                'organization_email': sub.organization.owner.email if sub.organization and sub.organization.owner else None,
                'plan_type': sub.plan_type,
                'billing_cycle': sub.billing_cycle,
                'status': sub.status,
                'payment_provider': sub.payment_provider or '—',
                'start_date': sub.start_date.isoformat(),
                'end_date': sub.end_date.isoformat() if sub.end_date else None,
                'cancel_at_period_end': sub.cancel_at_period_end,
            })

        return Response({
            'subscriptions': rows,
            'total': total,
            'paid_count': paid_count,
            'free_count': free_count,
            'plan_breakdown': plan_breakdown,
            'status_breakdown': status_breakdown,
            'page': page,
            'page_size': page_size,
        })
    return await _sync()


# ─── newsletter ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Admin Dashboard"],
    summary="Send Newsletter / Broadcast Email",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'subject': {'type': 'string'},
                'message': {'type': 'string'},
                'audience': {'type': 'string', 'enum': ['all', 'pro', 'free', 'enterprise', 'verified', 'unverified']},
                'action_url': {'type': 'string'},
                'action_text': {'type': 'string'},
            },
            'required': ['subject', 'message']
        }
    },
    responses={200: {'description': 'Queued successfully'}, 403: {'description': 'Forbidden'}}
)
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_newsletter_view(request):
    @sync_to_async
    def _sync():
        from core.tasks import send_email_task

        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()
        audience = request.data.get('audience', 'all')
        action_url = request.data.get('action_url', '').strip()
        action_text = request.data.get('action_text', 'Open BuildTracker').strip()

        if not subject or not message:
            return Response({'error': 'subject and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        qs = User.objects.filter(status='active', is_verified=True)
        if audience == 'pro':
            qs = qs.filter(plan_type='pro')
        elif audience == 'free':
            qs = qs.filter(plan_type='free')
        elif audience == 'enterprise':
            qs = qs.filter(plan_type='enterprise')
        elif audience == 'unverified':
            qs = User.objects.filter(is_verified=False)

        emails = list(qs.values_list('email', flat=True))
        if not emails:
            return Response({'error': 'No recipients found for this audience'}, status=status.HTTP_400_BAD_REQUEST)

        extra_context = {
            'email_type': 'general_update',
            'chip_label': 'BuildTracker Update',
            'action_url': action_url or None,
            'action_text': action_text,
        }

        # Send in batches of 50 via Celery
        batch_size = 50
        queued = 0
        for i in range(0, len(emails), batch_size):
            batch = emails[i:i + batch_size]
            send_email_task.delay(
                subject=subject,
                message=message,
                recipient_list=batch,
                fail_silently=True,
                extra_context=extra_context,
            )
            queued += len(batch)

        return Response({
            'message': f'Newsletter queued for {queued} recipients',
            'recipient_count': queued,
            'audience': audience,
        })
    return await _sync()


# ─── content hub ─────────────────────────────────────────────────────────────

def _content_row(p):
    return {
        'id': p.id,
        'platform': p.platform,
        'content_pillar': p.content_pillar,
        'tone': p.tone,
        'hook': p.hook,
        'full_copy': p.full_copy,
        'visual_direction': p.visual_direction,
        'hashtags': p.hashtags,
        'status': p.status,
        'priority': p.priority,
        'week': p.week,
        'day': p.day,
        'scheduled_date': p.scheduled_date.isoformat() if p.scheduled_date else None,
        'posted_date': p.posted_date.isoformat() if p.posted_date else None,
        'notes': p.notes,
        'updated_at': p.updated_at.isoformat(),
    }


@extend_schema(tags=["Admin Dashboard"], summary="List Content Posts")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_content_list_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Q
        page = int(request.query_params.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        platform = request.query_params.get('platform', '').strip()
        content_status = request.query_params.get('status', '').strip()

        qs = ContentPost.objects.all()
        if search:
            qs = qs.filter(Q(hook__icontains=search) | Q(content_pillar__icontains=search))
        if platform:
            qs = qs.filter(platform=platform)
        if content_status:
            qs = qs.filter(status=content_status)

        total = qs.count()
        posts = [_content_row(p) for p in qs.order_by('platform', 'id')[offset:offset + page_size]]
        return Response({'posts': posts, 'total': total, 'page': page, 'page_size': page_size})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update Content Post Status")
@api_view(['PATCH'])
@permission_classes([IsAdmin])
async def admin_content_update_view(request, post_id):
    @sync_to_async
    def _sync():
        try:
            post = ContentPost.objects.get(id=post_id)
        except ContentPost.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = ('status', 'priority', 'scheduled_date', 'posted_date', 'notes',
                          'hook', 'full_copy', 'hashtags')
        for field in allowed_fields:
            if field in request.data:
                setattr(post, field, request.data[field] or None if field.endswith('_date') else request.data[field])
        post.save()
        return Response(_content_row(post))
    return await _sync()


# ─── sales leads ─────────────────────────────────────────────────────────────

def _lead_row(lead):
    return {
        'id': lead.id,
        'priority': lead.priority,
        'company': lead.company,
        'website': lead.website,
        'sector': lead.sector,
        'stage': lead.stage,
        'city': lead.city,
        'target_title': lead.target_title,
        'linkedin_search_url': lead.linkedin_search_url,
        'pain_angle': lead.pain_angle,
        'dm_template': lead.dm_template,
        'status': lead.status,
        'date_contacted': lead.date_contacted.isoformat() if lead.date_contacted else None,
        'follow_up_date': lead.follow_up_date.isoformat() if lead.follow_up_date else None,
        'notes': lead.notes,
        'updated_at': lead.updated_at.isoformat(),
    }


@extend_schema(tags=["Admin Dashboard"], summary="List Sales Leads")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_leads_list_view(request):
    @sync_to_async
    def _sync():
        from django.db.models import Q
        page = int(request.query_params.get('page', 1))
        page_size = 25
        offset = (page - 1) * page_size
        search = request.query_params.get('search', '').strip()
        priority = request.query_params.get('priority', '').strip()
        lead_status = request.query_params.get('status', '').strip()
        sector = request.query_params.get('sector', '').strip()
        stage = request.query_params.get('stage', '').strip()

        qs = SalesLead.objects.all()
        if search:
            qs = qs.filter(Q(company__icontains=search) | Q(sector__icontains=search))
        if priority:
            qs = qs.filter(priority=priority)
        if lead_status:
            qs = qs.filter(status=lead_status)
        if sector:
            qs = qs.filter(sector__icontains=sector)
        if stage:
            qs = qs.filter(stage=stage)

        total = qs.count()
        leads = [_lead_row(l) for l in qs.order_by('priority', 'company')[offset:offset + page_size]]

        # Summary counts
        from django.db.models import Count
        status_summary = {
            row['status']: row['count']
            for row in SalesLead.objects.values('status').annotate(count=Count('id'))
        }
        priority_summary = {
            row['priority']: row['count']
            for row in SalesLead.objects.values('priority').annotate(count=Count('id'))
        }

        return Response({
            'leads': leads,
            'total': total,
            'page': page,
            'page_size': page_size,
            'status_summary': status_summary,
            'priority_summary': priority_summary,
        })
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update Sales Lead")
@api_view(['PATCH'])
@permission_classes([IsAdmin])
async def admin_lead_update_view(request, lead_id):
    @sync_to_async
    def _sync():
        try:
            lead = SalesLead.objects.get(id=lead_id)
        except SalesLead.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = ('status', 'notes', 'date_contacted', 'follow_up_date', 'priority')
        for field in allowed_fields:
            if field in request.data:
                val = request.data[field]
                if field.endswith('_date') and not val:
                    val = None
                setattr(lead, field, val)
        lead.save()
        return Response(_lead_row(lead))
    return await _sync()


# ─── lead contacts ────────────────────────────────────────────────────────────

def _contact_row(c):
    return {
        'id': c.id,
        'lead_id': c.lead_id,
        'name': c.name,
        'title': c.title,
        'linkedin_url': c.linkedin_url,
        'phone': c.phone,
        'email': c.email,
        'twitter_handle': c.twitter_handle,
        'outreach_status': c.outreach_status,
        'date_contacted': c.date_contacted.isoformat() if c.date_contacted else None,
        'follow_up_date': c.follow_up_date.isoformat() if c.follow_up_date else None,
        'notes': c.notes,
        'updated_at': c.updated_at.isoformat(),
    }


@extend_schema(tags=["Admin Dashboard"], summary="List contacts for a lead")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_lead_contacts_list_view(request, lead_id):
    @sync_to_async
    def _sync():
        if not SalesLead.objects.filter(id=lead_id).exists():
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)
        contacts = LeadContact.objects.filter(lead_id=lead_id).order_by('name')
        return Response({'contacts': [_contact_row(c) for c in contacts]})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Add a contact to a lead")
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_lead_contact_create_view(request, lead_id):
    @sync_to_async
    def _sync():
        try:
            lead = SalesLead.objects.get(id=lead_id)
        except SalesLead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import date, datetime
        def _parse_date(val):
            if not val:
                return None
            if isinstance(val, date):
                return val
            try:
                return datetime.strptime(str(val), '%Y-%m-%d').date()
            except Exception:
                return None

        contact = LeadContact.objects.create(
            lead=lead,
            name=name,
            title=request.data.get('title', '').strip(),
            linkedin_url=request.data.get('linkedin_url', '').strip(),
            phone=request.data.get('phone', '').strip(),
            email=request.data.get('email', '').strip(),
            twitter_handle=request.data.get('twitter_handle', '').strip(),
            outreach_status=request.data.get('outreach_status', 'not_contacted'),
            date_contacted=_parse_date(request.data.get('date_contacted')),
            follow_up_date=_parse_date(request.data.get('follow_up_date')),
            notes=request.data.get('notes', '').strip(),
        )
        return Response(_contact_row(contact), status=status.HTTP_201_CREATED)
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update a lead contact")
@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdmin])
async def admin_lead_contact_detail_view(request, lead_id, contact_id):
    @sync_to_async
    def _sync():
        try:
            contact = LeadContact.objects.get(id=contact_id, lead_id=lead_id)
        except LeadContact.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.method == 'DELETE':
            contact.delete()
            return Response({'message': 'Contact deleted'})

        allowed = ('name', 'title', 'linkedin_url', 'phone', 'email', 'twitter_handle',
                   'outreach_status', 'date_contacted', 'follow_up_date', 'notes')
        for field in allowed:
            if field in request.data:
                val = request.data[field]
                if field.endswith('_date') and not val:
                    val = None
                setattr(contact, field, val)
        contact.save()
        return Response(_contact_row(contact))
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Send email to a specific lead contact")
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_send_contact_email_view(request, lead_id, contact_id):
    @sync_to_async
    def _sync():
        try:
            contact = LeadContact.objects.select_related('lead').get(id=contact_id, lead_id=lead_id)
        except LeadContact.DoesNotExist:
            return Response({'error': 'Contact not found'}, status=status.HTTP_404_NOT_FOUND)

        if not contact.email:
            return Response({'error': 'This contact has no email address'}, status=status.HTTP_400_BAD_REQUEST)

        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()
        action_url = request.data.get('action_url', '').strip()
        action_text = request.data.get('action_text', 'Open BuildTracker').strip()

        if not subject or not message:
            return Response({'error': 'subject and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        from core.tasks import send_email_task
        send_email_task.delay(
            subject=subject,
            message=message,
            recipient_list=[contact.email],
            fail_silently=False,
            extra_context={
                'email_type': 'general_update',
                'chip_label': 'BuildTracker',
                'action_url': action_url or None,
                'action_text': action_text,
                'recipient_name': contact.name,
            },
        )

        # Mark contact as dm_sent / replied if still not_contacted
        if contact.outreach_status == 'not_contacted':
            from datetime import date
            contact.outreach_status = 'dm_sent'
            contact.date_contacted = date.today()
            contact.save(update_fields=['outreach_status', 'date_contacted'])

        return Response({
            'message': f'Email sent to {contact.name} ({contact.email})',
            'contact': _contact_row(contact),
        })
    return await _sync()


# ─── Plan Pricing ─────────────────────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="List current plan prices")
@api_view(['GET'])
@permission_classes([IsAdmin])
async def admin_pricing_list_view(request):
    """
    Return current prices for all active plans from the PlanPricing table.
    Any admin can view pricing.
    """
    @sync_to_async
    def _sync():
        from subscriptions.models import PlanPricing

        rows = PlanPricing.objects.select_related('updated_by').filter(is_active=True)
        data = []
        for p in rows:
            data.append({
                'plan_type':         p.plan_type,
                'plan_label':        p.get_plan_type_display(),
                'price_ngn_monthly': float(p.price_ngn_monthly),
                'price_ngn_yearly':  float(p.price_ngn_yearly),
                'price_usd_monthly': float(p.price_usd_monthly),
                'price_usd_yearly':  float(p.price_usd_yearly),
                'is_active':         p.is_active,
                'updated_at':        p.updated_at.isoformat() if p.updated_at else None,
                'updated_by':        p.updated_by.email if p.updated_by else None,
            })
        return Response({'pricing': data})
    return await _sync()


@extend_schema(tags=["Admin Dashboard"], summary="Update a plan's prices (requires password)")
@api_view(['PUT'])
@permission_classes([IsSuperAdmin])
async def admin_pricing_update_view(request, plan_type):
    """
    Update the prices for a single plan.

    Body:
        password         — current admin password (required for confirmation)
        price_ngn_monthly
        price_ngn_yearly   (per-month rate when billed yearly)
        price_usd_monthly
        price_usd_yearly   (per-month rate when billed yearly)

    Only super_admins can update prices; a correct password is required every time.
    The update is logged to the PlanPricing.updated_by field.
    """
    @sync_to_async
    def _sync():
        from django.contrib.auth.hashers import check_password
        from subscriptions.models import PlanPricing

        # 1. Verify the password
        password = request.data.get('password', '')
        if not password:
            return Response({'error': 'Your current password is required to change pricing.'}, status=status.HTTP_400_BAD_REQUEST)

        if not check_password(password, request.user.password):
            return Response({'error': 'Incorrect password. Price update was not saved.'}, status=status.HTTP_401_UNAUTHORIZED)

        # 2. Validate plan type
        valid_plans = ['starter', 'premium', 'custom']
        if plan_type not in valid_plans:
            return Response({'error': f'Unknown plan type. Must be one of: {valid_plans}'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Validate the numeric fields
        fields = ['price_ngn_monthly', 'price_ngn_yearly', 'price_usd_monthly', 'price_usd_yearly']
        values = {}
        for field in fields:
            raw = request.data.get(field)
            if raw is None:
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                val = float(raw)
                if val < 0:
                    raise ValueError
                values[field] = val
            except (ValueError, TypeError):
                return Response({'error': f'{field} must be a non-negative number'}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Update or create the record
        pricing, created = PlanPricing.objects.update_or_create(
            plan_type=plan_type,
            defaults={
                'price_ngn_monthly': values['price_ngn_monthly'],
                'price_ngn_yearly':  values['price_ngn_yearly'],
                'price_usd_monthly': values['price_usd_monthly'],
                'price_usd_yearly':  values['price_usd_yearly'],
                'is_active':         True,
                'updated_by':        request.user,
            }
        )

        return Response({
            'message': f"{'Created' if created else 'Updated'} {plan_type} pricing successfully.",
            'plan_type':         pricing.plan_type,
            'price_ngn_monthly': float(pricing.price_ngn_monthly),
            'price_ngn_yearly':  float(pricing.price_ngn_yearly),
            'price_usd_monthly': float(pricing.price_usd_monthly),
            'price_usd_yearly':  float(pricing.price_usd_yearly),
            'updated_at':        pricing.updated_at.isoformat(),
            'updated_by':        pricing.updated_by.email if pricing.updated_by else None,
        })
    return await _sync()


# ─── set subscription plan (admin override) ───────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Manually set a subscription plan for an organisation")
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_set_subscription_plan_view(request, subscription_id):
    @sync_to_async
    def _sync():
        from subscriptions.models import Subscription

        try:
            sub = Subscription.objects.select_related(
                'organization', 'organization__owner'
            ).get(id=subscription_id)
        except Subscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)

        plan_type    = request.data.get('plan_type')
        sub_status   = request.data.get('status')
        billing_cycle = request.data.get('billing_cycle')

        valid_plans   = ['free', 'starter', 'premium', 'custom', 'pro', 'business', 'enterprise']
        valid_statuses = ['active', 'inactive', 'cancelled', 'past_due']
        valid_cycles  = ['monthly', 'yearly']

        if plan_type and plan_type not in valid_plans:
            return Response({'error': 'Invalid plan_type'}, status=status.HTTP_400_BAD_REQUEST)
        if sub_status and sub_status not in valid_statuses:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        if billing_cycle and billing_cycle not in valid_cycles:
            return Response({'error': 'Invalid billing_cycle'}, status=status.HTTP_400_BAD_REQUEST)

        if not any([plan_type, sub_status, billing_cycle]):
            return Response({'error': 'Nothing to update'}, status=status.HTTP_400_BAD_REQUEST)

        if plan_type:
            sub.plan_type = plan_type
            # Keep org and owner in sync
            sub.organization.plan_type = plan_type
            sub.organization.save(update_fields=['plan_type'])
            if sub.organization.owner:
                sub.organization.owner.plan_type = plan_type
                sub.organization.owner.save(update_fields=['plan_type'])

        if sub_status:
            sub.status = sub_status

        if billing_cycle:
            sub.billing_cycle = billing_cycle

        sub.save()

        return Response({
            'message': f"Subscription for {sub.organization.name} updated.",
            'id': str(sub.id),
            'plan_type': sub.plan_type,
            'status': sub.status,
            'billing_cycle': sub.billing_cycle,
        })
    return await _sync()


# ─── send email to an individual ─────────────────────────────────────────────

@extend_schema(tags=["Admin Dashboard"], summary="Send a direct email to any individual")
@api_view(['POST'])
@permission_classes([IsAdmin])
async def admin_send_user_email_view(request):
    @sync_to_async
    def _sync():
        from core.tasks import send_email_task

        email       = request.data.get('email', '').strip()
        subject     = request.data.get('subject', '').strip()
        message     = request.data.get('message', '').strip()
        action_url  = request.data.get('action_url', '').strip()
        action_text = request.data.get('action_text', 'Open BuildTracker').strip()

        if not email or not subject or not message:
            return Response(
                {'error': 'email, subject, and message are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Personalise greeting if recipient is a known user
        recipient_name = None
        try:
            u = User.objects.get(email=email)
            recipient_name = f"{u.first_name} {u.last_name}".strip() or u.email
        except User.DoesNotExist:
            pass

        send_email_task.delay(
            subject=subject,
            message=message,
            recipient_list=[email],
            fail_silently=False,
            extra_context={
                'email_type': 'general_update',
                'chip_label': 'BuildTracker',
                'action_url': action_url or None,
                'action_text': action_text,
                'recipient_name': recipient_name,
            },
        )

        return Response({'message': f'Email sent to {email}'})
    return await _sync()
