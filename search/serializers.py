from rest_framework import serializers

class SearchResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    content = serializers.CharField()
    type = serializers.CharField()
    workspace_id = serializers.UUIDField(allow_null=True)
    workspace_name = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    relevance_score = serializers.FloatField(default=1.0)
    url = serializers.CharField()

class SearchCategoriesSerializer(serializers.Serializer):
    tasks = serializers.IntegerField()
    wiki = serializers.IntegerField()
    integrations = serializers.IntegerField()

class SearchSuggestionsSerializer(serializers.Serializer):
    suggestions = serializers.ListField(child=serializers.CharField())