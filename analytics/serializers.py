from rest_framework import serializers

class DashboardStatsSerializer(serializers.Serializer):
    totalTasks = serializers.IntegerField()
    completedTasks = serializers.IntegerField()
    inProgressTasks = serializers.IntegerField()
    overdueTasks = serializers.IntegerField()
    blockedTasks = serializers.IntegerField()
    totalMembers = serializers.IntegerField()
    velocity = serializers.FloatField()
    healthScore = serializers.FloatField()
    milestoneProgress = serializers.ListField(child=serializers.JSONField())
    sprintProgress = serializers.ListField(child=serializers.JSONField())

class ChartDataSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.FloatField()
    date = serializers.DateField(required=False)
    color = serializers.CharField(required=False)

class PerformanceDataSerializer(serializers.Serializer):
    member_name = serializers.CharField()
    tasks_completed = serializers.IntegerField()
    avg_completion_time = serializers.FloatField()
    efficiency_score = serializers.FloatField()

class DashboardChartsSerializer(serializers.Serializer):
    statusData = ChartDataSerializer(many=True)
    priorityData = ChartDataSerializer(many=True)
    trendData = ChartDataSerializer(many=True)
    memberPerformance = PerformanceDataSerializer(many=True)
    milestoneChart = ChartDataSerializer(many=True)
    sprintChart = ChartDataSerializer(many=True)

class BottleneckDataSerializer(serializers.Serializer):
    area = serializers.CharField()
    severity = serializers.ChoiceField(choices=['low', 'medium', 'high'])
    description = serializers.CharField()
    impact_score = serializers.FloatField()

class MilestoneMetricsSerializer(serializers.Serializer):
    milestone_id = serializers.IntegerField()
    milestone_name = serializers.CharField()
    completion_rate = serializers.FloatField()
    on_track = serializers.BooleanField()
    estimated_completion = serializers.DateField()

class SprintMetricsSerializer(serializers.Serializer):
    sprint_id = serializers.IntegerField()
    sprint_name = serializers.CharField()
    velocity = serializers.FloatField()
    burndown_rate = serializers.FloatField()
    completion_rate = serializers.FloatField()

class PerformanceAnalyticsSerializer(serializers.Serializer):
    completionRate = serializers.FloatField()
    averageTaskTime = serializers.FloatField()
    teamEfficiency = serializers.FloatField()
    bottlenecks = BottleneckDataSerializer(many=True)
    milestoneMetrics = MilestoneMetricsSerializer(many=True)
    sprintMetrics = SprintMetricsSerializer(many=True)

class TrendDataSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.FloatField()
    change_percentage = serializers.FloatField()

class TrendsAnalyticsSerializer(serializers.Serializer):
    taskCreationTrend = TrendDataSerializer(many=True)
    completionTrend = TrendDataSerializer(many=True)
    velocityTrend = TrendDataSerializer(many=True)
    milestoneTrend = TrendDataSerializer(many=True)