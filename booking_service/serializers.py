from rest_framework import serializers

from .models import BookingRequest, LSAProfile


class BookingRequestCreateSerializer(serializers.Serializer):
    parent = serializers.IntegerField(min_value=1)
    lsa = serializers.IntegerField(min_value=1)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs['end_time'] <= attrs['start_time']:
            raise serializers.ValidationError(
                {'end_time': 'end_time must be strictly after start_time.'}
            )
        return attrs


class BookingRequestSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    lsa_name = serializers.CharField(source='lsa.name', read_only=True)

    class Meta:
        model = BookingRequest
        fields = [
            'id',
            'parent',
            'parent_name',
            'lsa',
            'lsa_name',
            'start_time',
            'end_time',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class LSASearchQuerySerializer(serializers.Serializer):
    skill = serializers.CharField(required=False, allow_blank=False)
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        if bool(start_time) != bool(end_time):
            raise serializers.ValidationError(
                "start_time and end_time must be provided together."
            )

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {'end_time': 'end_time must be strictly after start_time.'}
            )

        return attrs


class LSAProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LSAProfile
        fields = [
            'id',
            'name',
            'email',
            'skills',
            'experience',
            'is_active',
            'created_at',
        ]
        read_only_fields = fields
