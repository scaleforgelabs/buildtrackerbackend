from html.parser import HTMLParser
from rest_framework import serializers
from django.utils.timezone import localtime
from .models import DailyCheckIn, CheckInBlocker
from tasks.models import Task


# ---------------------------------------------------------------------------
# HTML → list-of-strings helper (strips Tiptap HTML into readable bullet lines)
# ---------------------------------------------------------------------------

class _HTMLToLines(HTMLParser):
    """Strips HTML tags and collects non-empty paragraph/list-item text."""
    BLOCK_TAGS = {'p', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'br'}

    def __init__(self):
        super().__init__()
        self._buf = []
        self._lines = []

    def handle_data(self, data):
        self._buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK_TAGS:
            text = ''.join(self._buf).strip()
            if text:
                self._lines.append(text)
            self._buf = []

    def get_lines(self):
        # Catch any trailing text not closed by a block tag
        remaining = ''.join(self._buf).strip()
        if remaining:
            self._lines.append(remaining)
        return self._lines or []


def html_to_lines(html: str) -> list:
    """Convert Tiptap HTML to a plain list of strings for the card display."""
    if not html:
        return []
    parser = _HTMLToLines()
    parser.feed(html)
    return parser.get_lines()


# ---------------------------------------------------------------------------
# Sentiment map
# ---------------------------------------------------------------------------

SENTIMENT_MAP = {
    'CRUSHING': {'emoji': '🚀', 'label': 'CRUSHING'},
    'GOOD':     {'emoji': '😇', 'label': 'GOOD'},
    'OKAY':     {'emoji': '😐', 'label': 'OKAY'},
    'LOW':      {'emoji': '😔', 'label': 'LOW'},
}

PRIORITY_MAP = {
    'HIGH': 'high',
    'MED':  'medium',
    'LOW':  'low',
}


# ---------------------------------------------------------------------------
# Blocker serializers
# ---------------------------------------------------------------------------

class CheckInBlockerCreateSerializer(serializers.Serializer):
    description = serializers.CharField()
    notify_member_id = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=['HIGH', 'MED', 'LOW'], default='HIGH')


class CheckInBlockerReadSerializer(serializers.ModelSerializer):
    """Shapes a blocker to match BlockerCardProps on the frontend."""
    message = serializers.SerializerMethodField()
    mention = serializers.SerializerMethodField()
    priority = serializers.SerializerMethodField()

    class Meta:
        model = CheckInBlocker
        fields = ['message', 'mention', 'priority']

    def get_message(self, obj):
        return obj.description

    def get_mention(self, obj):
        if obj.notify_member:
            return f"@{obj.notify_member.first_name} {obj.notify_member.last_name}".strip()
        return "#Everybody"

    def get_priority(self, obj):
        return PRIORITY_MAP.get(obj.priority, 'low')


# ---------------------------------------------------------------------------
# Task tag helper serializer
# ---------------------------------------------------------------------------

class TaskTagSerializer(serializers.ModelSerializer):
    """Returns { id: ticket_number, title: task_name } to match TaskTagProps."""
    id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ['id', 'title']

    def get_id(self, obj):
        return str(obj.ticket_number)

    def get_title(self, obj):
        return obj.task_name


# ---------------------------------------------------------------------------
# Create serializer (POST payload from the form)
# ---------------------------------------------------------------------------

class DailyCheckInCreateSerializer(serializers.Serializer):
    sentiment = serializers.ChoiceField(
        choices=['GREAT', 'GOOD', 'NEUTRAL', 'BAD', 'TERRIBLE'],
        default='GOOD'
    )
    yesterday_progress = serializers.CharField(allow_blank=True, default='')
    yesterday_task_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    tomorrow_plan = serializers.CharField(allow_blank=True, default='')
    tomorrow_task_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    has_blockers = serializers.BooleanField(default=False)
    blockers = serializers.ListField(
        child=CheckInBlockerCreateSerializer(), required=False, default=list
    )

    def validate(self, data):
        workspace = self.context['workspace']
        user = self.context['request'].user
        from django.utils import timezone
        today = timezone.now().date()
        if DailyCheckIn.objects.filter(workspace=workspace, user=user, date=today).exists():
            raise serializers.ValidationError(
                "You have already submitted a check-in for today."
            )
        return data

    def create(self, validated_data):
        workspace = self.context['workspace']
        user = self.context['request'].user

        yesterday_task_ids = validated_data.pop('yesterday_task_ids', [])
        tomorrow_task_ids = validated_data.pop('tomorrow_task_ids', [])
        blocker_data_list = validated_data.pop('blockers', [])

        checkin = DailyCheckIn.objects.create(
            workspace=workspace,
            user=user,
            sentiment=validated_data['sentiment'],
            yesterday_progress=validated_data.get('yesterday_progress', ''),
            tomorrow_plan=validated_data.get('tomorrow_plan', ''),
            has_blockers=validated_data.get('has_blockers', False),
        )

        # Link tasks (only tasks belonging to this workspace)
        if yesterday_task_ids:
            yt = Task.objects.filter(id__in=yesterday_task_ids, workspace=workspace)
            checkin.yesterday_tasks.set(yt)

        if tomorrow_task_ids:
            tt = Task.objects.filter(id__in=tomorrow_task_ids, workspace=workspace)
            checkin.tomorrow_tasks.set(tt)

        # Create blockers
        for bd in blocker_data_list:
            notify_id = bd.get('notify_member_id')
            notify_user = None
            if notify_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    notify_user = User.objects.get(id=notify_id)
                except User.DoesNotExist:
                    pass
            CheckInBlocker.objects.create(
                checkin=checkin,
                description=bd['description'],
                notify_member=notify_user,
                priority=bd.get('priority', 'HIGH'),
            )

        return checkin


# ---------------------------------------------------------------------------
# Feed serializer (GET — shapes data to match CheckInItem interface)
# ---------------------------------------------------------------------------

class DailyCheckInFeedSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    sentiment = serializers.SerializerMethodField()
    accomplishments = serializers.SerializerMethodField()
    accomplishmentTasks = serializers.SerializerMethodField()
    plans = serializers.SerializerMethodField()
    planTasks = serializers.SerializerMethodField()
    blockers = serializers.SerializerMethodField()

    class Meta:
        model = DailyCheckIn
        fields = [
            'id', 'user', 'time', 'status', 'sentiment',
            'accomplishments', 'accomplishmentTasks',
            'plans', 'planTasks', 'blockers',
        ]

    def get_user(self, obj):
        u = obj.user
        
        # Optimization: Use pre-fetched member roles from context if available
        member_roles = self.context.get('member_roles', {})
        role = member_roles.get(u.id)
        
        # Fallback to DB query if not in context (should rarely happen with new view logic)
        if role is None:
            try:
                from workspaces.models import WorkspaceMember
                member = WorkspaceMember.objects.get(workspace=obj.workspace, user=u)
                role = member.job_role or member.role or ''
            except Exception:
                role = u.role or ''

        avatar_url = None
        if u.avatar:
            request = self.context.get('request')
            if request:
                avatar_url = request.build_absolute_uri(u.avatar.url)
            else:
                avatar_url = u.avatar.url

        return {
            'first_name': u.first_name or '',
            'last_name': u.last_name or '',
            'avatar': avatar_url,
            'role': role,
        }

    def get_time(self, obj):
        return localtime(obj.created_at).strftime('%I:%M %p')

    def get_status(self, obj):
        return 'BLOCKED' if obj.has_blockers else 'ACTIVE'

    def get_sentiment(self, obj):
        return SENTIMENT_MAP.get(obj.sentiment, {'emoji': '😊', 'label': obj.sentiment})

    def get_accomplishments(self, obj):
        return html_to_lines(obj.yesterday_progress) or ['No update provided.']

    def get_accomplishmentTasks(self, obj):
        return TaskTagSerializer(obj.yesterday_tasks.all(), many=True).data

    def get_plans(self, obj):
        return html_to_lines(obj.tomorrow_plan) or ['No plan provided.']

    def get_planTasks(self, obj):
        return TaskTagSerializer(obj.tomorrow_tasks.all(), many=True).data

    def get_blockers(self, obj):
        if not obj.has_blockers:
            return []
        return CheckInBlockerReadSerializer(obj.blockers.all(), many=True).data
