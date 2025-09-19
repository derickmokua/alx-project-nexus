from rest_framework import serializers
from django.db import transaction, models
from .models import Poll, PollOption, Vote


class PollOptionSerializer(serializers.ModelSerializer):
    percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = PollOption
        fields = ['id', 'text', 'order', 'vote_count', 'percentage']
        read_only_fields = ['vote_count']
    
    def get_percentage(self, obj):
        if obj.poll.total_votes == 0:
            return 0.0
        return round((obj.vote_count / obj.poll.total_votes) * 100, 2)


class PollCreateSerializer(serializers.ModelSerializer):
    options = serializers.ListField(
        child=serializers.CharField(max_length=255),
        min_length=2,
        max_length=10
    )
    
    class Meta:
        model = Poll
        fields = ['title', 'description', 'expires_at', 'allow_multiple_votes', 'options']
    
    def validate_options(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Poll options must be unique")
        return value
    
    def create(self, validated_data):
        options_data = validated_data.pop('options')
        poll = Poll.objects.create(**validated_data)
        
        for index, option_text in enumerate(options_data):
            PollOption.objects.create(poll=poll, text=option_text, order=index)
        
        return poll


class PollDetailSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True, read_only=True)
    created_by = serializers.StringRelatedField()
    is_expired = serializers.ReadOnlyField()
    can_vote = serializers.ReadOnlyField()
    user_has_voted = serializers.SerializerMethodField()
    
    class Meta:
        model = Poll
        fields = [
            'id', 'title', 'description', 'created_by', 'created_at',
            'updated_at', 'expires_at', 'is_active', 'allow_multiple_votes',
            'total_votes', 'is_expired', 'can_vote', 'options', 'user_has_voted'
        ]
    
    def get_user_has_voted(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        
        if request.user.is_authenticated:
            return Vote.objects.filter(poll=obj, user=request.user).exists()
        
        session_key = request.session.session_key
        if session_key:
            return Vote.objects.filter(poll=obj, session_key=session_key).exists()
        
        return False


class VoteSerializer(serializers.ModelSerializer):
    option_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Vote
        fields = ['option_id']
    
    def validate_option_id(self, value):
        try:
            option = PollOption.objects.get(id=value)
            poll_id = self.context['poll_id']
            
            if option.poll.id != poll_id:
                raise serializers.ValidationError("Option does not belong to this poll")
            
            if not option.poll.can_vote:
                raise serializers.ValidationError("Voting is not allowed for this poll")
            
            return value
        except PollOption.DoesNotExist:
            raise serializers.ValidationError("Invalid option selected")
    
    def create(self, validated_data):
        option_id = validated_data['option_id']
        poll_id = self.context['poll_id']
        request = self.context['request']
        
        option = PollOption.objects.select_for_update().get(id=option_id)
        poll = Poll.objects.select_for_update().get(id=poll_id)
        
        # Check for existing vote
        vote_filter = {'poll': poll}
        if request.user.is_authenticated:
            vote_filter['user'] = request.user
        else:
            if not request.session.session_key:
                request.session.create()
            vote_filter['session_key'] = request.session.session_key
        
        existing_vote = Vote.objects.filter(**vote_filter).first()
        
        if existing_vote and not poll.allow_multiple_votes:
            raise serializers.ValidationError("You have already voted in this poll")
        
        with transaction.atomic():
            if existing_vote and poll.allow_multiple_votes:
                # Update existing vote
                old_option = PollOption.objects.select_for_update().get(id=existing_vote.option.id)
                existing_vote.option = option
                existing_vote.save()
                
                # Update counts
                old_option.vote_count = models.F('vote_count') - 1
                old_option.save(update_fields=['vote_count'])
                option.vote_count = models.F('vote_count') + 1
                option.save(update_fields=['vote_count'])
                
                return existing_vote
            else:
                # Create new vote
                vote_data = {
                    'poll': poll,
                    'option': option,
                    'ip_address': request.META.get('REMOTE_ADDR')
                }
                
                if request.user.is_authenticated:
                    vote_data['user'] = request.user
                else:
                    vote_data['session_key'] = request.session.session_key
                
                vote = Vote.objects.create(**vote_data)
                
                # Update counts
                option.vote_count = models.F('vote_count') + 1
                option.save(update_fields=['vote_count'])
                poll.total_votes = models.F('total_votes') + 1
                poll.save(update_fields=['total_votes'])
                
                return vote
