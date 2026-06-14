from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.campaigns.forms import CampaignForm
from apps.campaigns.models import Campaign, EmailClickEvent, EmailEngagement
from apps.senders.models import Sender


class CampaignFlowTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			email='owner@example.com',
			username='owner',
			first_name='Owner',
			last_name='User',
			password='pass12345',
		)
		self.sender = Sender.objects.create(
			user=self.user,
			display_name='Main Sender',
			from_email='sender@example.com',
			provider='custom',
			smtp_host='smtp.example.com',
			smtp_port=587,
			username='sender@example.com',
			_password='mocked',
			use_tls=True,
			is_active=True,
		)
		self.client.force_login(self.user)

	def _base_campaign_payload(self):
		return {
			'name': 'Spring Launch',
			'subject': 'Hello from Mailexa',
			'from_name': 'Mailexa Team',
			'reply_to': 'reply@example.com',
			'recipient_emails': 'alpha@example.com, beta@example.com',
			'body_text': 'Campaign body text',
			'sender': str(self.sender.id),
			'scheduled_at': '',
			'action': 'save_draft',
		}

	def test_schedule_time_must_be_future(self):
		payload = self._base_campaign_payload()
		payload['scheduled_at'] = '2000-01-01T00:00'
		form = CampaignForm(data=payload, user=self.user)
		self.assertFalse(form.is_valid())
		self.assertIn('Schedule time must be in the future.', form.errors.get('scheduled_at', []))

	def test_campaign_send_guardrail_blocks_empty_recipients(self):
		campaign = Campaign.objects.create(
			user=self.user,
			sender=self.sender,
			name='No Recipients',
			subject='Subject',
			body_text='Body',
			recipient_emails='',
			status='draft',
		)
		response = self.client.post(reverse('campaigns:campaign_send', args=[campaign.id]), follow=True)
		self.assertEqual(response.status_code, 200)
		messages = [m.message for m in get_messages(response.wsgi_request)]
		self.assertTrue(any('valid recipient email' in msg.lower() for msg in messages))

	def test_campaign_list_paginates_and_filters(self):
		for idx in range(12):
			Campaign.objects.create(
				user=self.user,
				sender=self.sender,
				name=f'Campaign {idx}',
				subject='Generic Subject',
				body_text='Body',
				recipient_emails='x@example.com',
				status='draft',
			)
		Campaign.objects.create(
			user=self.user,
			sender=self.sender,
			name='Special Offer',
			subject='Special Subject',
			body_text='Body',
			recipient_emails='special@example.com',
			status='sent',
		)

		page_response = self.client.get(reverse('campaigns:campaign_list'))
		self.assertEqual(page_response.status_code, 200)
		self.assertEqual(len(page_response.context['campaigns']), 10)

		filtered = self.client.get(reverse('campaigns:campaign_list'), {'q': 'Special', 'status': 'sent'})
		self.assertEqual(filtered.status_code, 200)
		self.assertEqual(len(filtered.context['campaigns']), 1)
		self.assertEqual(filtered.context['campaigns'][0].name, 'Special Offer')

	@patch('apps.campaigns.views.campaign.send_test_email_with_smtp')
	def test_send_test_action_calls_test_sender(self, mock_send_test):
		payload = self._base_campaign_payload()
		payload['action'] = 'send_test'
		payload['test_email'] = 'preview@example.com'

		response = self.client.post(reverse('campaigns:campaign_create'), data=payload)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(Campaign.objects.count(), 1)
		campaign = Campaign.objects.first()
		self.assertEqual(campaign.status, 'draft')
		mock_send_test.assert_called_once()
		args, _ = mock_send_test.call_args
		self.assertEqual(args[0].id, campaign.id)
		self.assertEqual(args[1], 'preview@example.com')

	@patch('apps.campaigns.views.send.async_send_campaign')
	def test_retry_failed_only_targets_unsent_recipients(self, mock_async):
		campaign = Campaign.objects.create(
			user=self.user,
			sender=self.sender,
			name='Retry Campaign',
			subject='Retry',
			body_text='Body',
			recipient_emails='a@example.com, b@example.com, c@example.com',
			status='sent',
			total_recipients=3,
			sent_count=1,
		)
		EmailEngagement.objects.create(
			campaign=campaign,
			recipient_email='a@example.com',
			tracking_token='tok-a',
		)

		response = self.client.post(reverse('campaigns:campaign_retry_failed', args=[campaign.id]))
		self.assertEqual(response.status_code, 302)
		self.assertTrue(mock_async.delay.called)
		args, kwargs = mock_async.delay.call_args
		self.assertEqual(kwargs.get('recipients_override'), ['b@example.com', 'c@example.com'])

	def test_analytics_export_links_csv(self):
		campaign = Campaign.objects.create(
			user=self.user,
			sender=self.sender,
			name='Analytics Campaign',
			subject='Analytics',
			body_text='Body',
			recipient_emails='a@example.com',
			status='sent',
		)
		engagement = EmailEngagement.objects.create(
			campaign=campaign,
			recipient_email='a@example.com',
			tracking_token='tok-1',
		)
		EmailClickEvent.objects.create(campaign=campaign, engagement=engagement, clicked_url='https://example.com/a')
		EmailClickEvent.objects.create(campaign=campaign, engagement=engagement, clicked_url='https://example.com/a')

		response = self.client.get(reverse('campaigns:campaign_analytics_export_csv', args=[campaign.id]), {'type': 'links'})
		self.assertEqual(response.status_code, 200)
		body = response.content.decode('utf-8')
		self.assertIn('clicked_url,total_clicks', body)
		self.assertIn('https://example.com/a,2', body)
