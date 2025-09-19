from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Poll, PollOption, Vote
from .serializers import (
    PollCreateSerializer, PollDetailSerializer, 
    VoteSerializer
)


class PollListCreateView(generics.ListCreateAPIView):
    """List all polls or create a new poll"""
    queryset = Poll.objects.filter(is_active=True)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PollCreateSerializer
        return PollDetailSerializer
    
    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(created_by=self.request.user)
        else:
            from django.contrib.auth.models import User
            anon_user, _ = User.objects.get_or_create(
                username='anonymous',
                defaults={'first_name': 'Anonymous', 'last_name': 'User'}
            )
            serializer.save(created_by=anon_user)


class PollDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a specific poll"""
    queryset = Poll.objects.all()
    serializer_class = PollDetailSerializer


@swagger_auto_schema(
    method='post',
    operation_description="Cast a vote for a specific poll option",
    request_body=VoteSerializer,
    responses={
        201: "Vote cast successfully",
        400: "Bad Request"
    }
)
@api_view(['POST'])
def vote_on_poll(request, poll_id):
    """Cast a vote on a specific poll"""
    poll = get_object_or_404(Poll, id=poll_id)
    
    if not poll.can_vote:
        return Response(
            {"error": "Voting is not allowed for this poll"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = VoteSerializer(
        data=request.data,
        context={'request': request, 'poll_id': poll_id}
    )
    
    if serializer.is_valid():
        try:
            serializer.save()
            return Response(
                {"message": "Vote cast successfully"}, 
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def poll_results(request, poll_id):
    """Get real-time results for a specific poll"""
    poll = get_object_or_404(Poll, id=poll_id)
    options = poll.options.all().order_by('order')
    
    results = []
    for option in options:
        percentage = 0.0
        if poll.total_votes > 0:
            percentage = round((option.vote_count / poll.total_votes) * 100, 2)
        
        results.append({
            'option_id': option.id,
            'option_text': option.text,
            'vote_count': option.vote_count,
            'percentage': percentage
        })
    
    return Response({
        'poll_id': poll.id,
        'title': poll.title,
        'total_votes': poll.total_votes,
        'results': results
    })
