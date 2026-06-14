from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.contacts.models import Contact, ContactList
from apps.automations.models import Workflow, WorkflowNode, WorkflowEdge, WorkflowEnrollment
from apps.automations.engine import process_workflow_enrollments, enroll_contact


class WorkflowModelTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        self.workflow = Workflow.objects.create(
            user=self.user,
            name='Test Workflow'
        )

    def test_workflow_creation(self):
        self.assertEqual(self.workflow.name, 'Test Workflow')
        self.assertTrue(self.workflow.is_active)

    def test_workflow_node_creation(self):
        node = WorkflowNode.objects.create(
            workflow=self.workflow,
            node_id='trigger_1',
            type='trigger',
            config={'event': 'list_signup'}
        )
        self.assertEqual(node.type, 'trigger')
        self.assertEqual(node.config['event'], 'list_signup')

    def test_workflow_edge_creation(self):
        node_a = WorkflowNode.objects.create(
            workflow=self.workflow,
            node_id='node_a',
            type='trigger',
        )
        node_b = WorkflowNode.objects.create(
            workflow=self.workflow,
            node_id='node_b',
            type='delay',
            config={'hours': 24}
        )
        edge = WorkflowEdge.objects.create(
            workflow=self.workflow,
            from_node_id=node_a.node_id,
            to_node_id=node_b.node_id,
        )
        self.assertEqual(edge.from_node_id, 'node_a')
        self.assertEqual(edge.to_node_id, 'node_b')

    def test_enrollment_state_transition(self):
        contact_list = ContactList.objects.create(
            user=self.user,
            name='Test List'
        )
        contact = Contact.objects.create(
            contact_list=contact_list,
            email='test@example.com',
            is_active=True
        )
        enrollment = WorkflowEnrollment.objects.create(
            contact=contact,
            workflow=self.workflow,
            status='active'
        )
        self.assertEqual(enrollment.status, 'active')

        enrollment.status = 'completed'
        enrollment.save()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')

    def test_enrollment_next_execution(self):
        contact_list = ContactList.objects.create(
            user=self.user,
            name='Test List'
        )
        contact = Contact.objects.create(
            contact_list=contact_list,
            email='test2@example.com',
            is_active=True
        )
        future = timezone.now() + timedelta(hours=2)
        enrollment = WorkflowEnrollment.objects.create(
            contact=contact,
            workflow=self.workflow,
            status='active',
            next_execution_at=future
        )
        self.assertIsNotNone(enrollment.next_execution_at)
        self.assertTrue(enrollment.next_execution_at > timezone.now())


class WorkflowEngineTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='engineuser',
            email='engine@example.com',
            password='testpass123',
        )
        self.contact_list = ContactList.objects.create(
            user=self.user,
            name='Engine Test List'
        )
        self.contact = Contact.objects.create(
            contact_list=self.contact_list,
            email='engine@test.com',
            is_active=True,
        )

        self.workflow = Workflow.objects.create(
            user=self.user,
            name='Engine Test WF',
            is_active=True,
        )

    def _make_node(self, node_id, type, config=None):
        return WorkflowNode.objects.create(
            workflow=self.workflow,
            node_id=node_id,
            type=type,
            config=config or {},
        )

    def _make_edge(self, from_id, to_id, condition='default'):
        return WorkflowEdge.objects.create(
            workflow=self.workflow,
            from_node_id=from_id,
            to_node_id=to_id,
            condition=condition,
        )

    def _create_enrollment(self, status='active', current_node_id=None, next_execution_at=None):
        if next_execution_at is None:
            next_execution_at = timezone.now() - timedelta(minutes=5)
        return WorkflowEnrollment.objects.create(
            contact=self.contact,
            workflow=self.workflow,
            status=status,
            current_node_id=current_node_id,
            next_execution_at=next_execution_at,
        )

    def test_process_no_ready_enrollments(self):
        result = process_workflow_enrollments()
        self.assertEqual(result, 0)

    def test_process_skips_future_enrollments(self):
        self._create_enrollment(next_execution_at=timezone.now() + timedelta(hours=1))
        result = process_workflow_enrollments()
        self.assertEqual(result, 0)

    def test_process_skips_non_active_enrollments(self):
        self._create_enrollment(status='completed')
        result = process_workflow_enrollments()
        self.assertEqual(result, 0)

    def test_process_trigger_to_delay(self):
        trigger = self._make_node('trig_1', 'trigger', {'event': 'list_signup'})
        delay = self._make_node('delay_1', 'delay', {'hours': 48})
        self._make_edge('trig_1', 'delay_1')

        enrollment = self._create_enrollment(current_node_id=None)
        result = process_workflow_enrollments()
        self.assertEqual(result, 1)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.current_node_id, 'trig_1')
        self.assertIsNotNone(enrollment.next_execution_at)

        result = process_workflow_enrollments()
        self.assertEqual(result, 1)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.current_node_id, 'delay_1')
        expected = timezone.now() + timedelta(hours=48)
        self.assertAlmostEqual(
            enrollment.next_execution_at.timestamp(),
            expected.timestamp(),
            delta=2,
        )

    def test_process_completes_after_last_node(self):
        trigger = self._make_node('trig_1', 'trigger', {'event': 'list_signup'})
        self._make_node('action_1', 'action', {'action': 'add_tag', 'tags': ['vip']})
        self._make_edge('trig_1', 'action_1')

        enrollment = self._create_enrollment(current_node_id=None)
        process_workflow_enrollments()
        process_workflow_enrollments()
        process_workflow_enrollments()

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')
        self.assertIsNone(enrollment.current_node_id)
        self.assertIsNone(enrollment.next_execution_at)

    def test_process_completes_with_no_edges(self):
        self._make_node('trig_1', 'trigger')
        enrollment = self._create_enrollment(current_node_id=None)
        process_workflow_enrollments()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.current_node_id, 'trig_1')
        process_workflow_enrollments()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')

    def test_process_completes_with_missing_next_node(self):
        self._make_node('trig_1', 'trigger')
        self._make_edge('trig_1', 'ghost_node')
        enrollment = self._create_enrollment(current_node_id=None)
        process_workflow_enrollments()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.current_node_id, 'trig_1')
        process_workflow_enrollments()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')

    def test_enroll_contact_creates_active_enrollment(self):
        enrollment = enroll_contact(self.contact, self.workflow)
        self.assertEqual(enrollment.status, 'active')
        self.assertIsNotNone(enrollment.next_execution_at)

    def test_enroll_contact_reactivates_paused(self):
        enrollment = WorkflowEnrollment.objects.create(
            contact=self.contact,
            workflow=self.workflow,
            status='paused',
        )
        result = enroll_contact(self.contact, self.workflow)
        result.refresh_from_db()
        self.assertEqual(result.status, 'active')

    def test_enroll_contact_resumes_completed(self):
        enrollment = WorkflowEnrollment.objects.create(
            contact=self.contact,
            workflow=self.workflow,
            status='completed',
        )
        result = enroll_contact(self.contact, self.workflow)
        result.refresh_from_db()
        self.assertEqual(result.status, 'active')
        self.assertIsNotNone(result.next_execution_at)

    def test_enroll_contact_does_not_duplicate_active(self):
        enrollment = WorkflowEnrollment.objects.create(
            contact=self.contact,
            workflow=self.workflow,
            status='active',
        )
        result = enroll_contact(self.contact, self.workflow)
        self.assertEqual(result.id, enrollment.id)
        self.assertEqual(result.status, 'active')

    def test_process_multiple_enrollments(self):
        trigger = self._make_node('trig_1', 'trigger')
        self._make_edge('trig_1', 'end')
        self._make_node('end', 'action', {'action': 'add_tag', 'tags': ['done']})

        contact2 = Contact.objects.create(
            contact_list=self.contact_list,
            email='contact2@test.com',
            is_active=True,
        )
        e1 = self._create_enrollment(current_node_id=None)
        e2 = WorkflowEnrollment.objects.create(
            contact=contact2,
            workflow=self.workflow,
            status='active',
            next_execution_at=timezone.now() - timedelta(minutes=5),
        )
        result = process_workflow_enrollments()
        self.assertEqual(result, 2)
