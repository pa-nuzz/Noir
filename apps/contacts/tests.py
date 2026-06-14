from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()

from apps.contacts.models import (
    Contact, ContactList, ContactTag,
    ContactCustomField, ContactSegment, ContactCustomFieldValue,
)
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspacePermission
from core.tenant import set_current_tenant, clear_current_tenant, tenant_context


class ContactModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='pass')
        self.list = ContactList.objects.create(user=self.user, name='Test List')
        self.contact = Contact.objects.create(
            contact_list=self.list, email='test@example.com',
            first_name='Test', last_name='User',
        )

    def test_contact_creation(self):
        self.assertEqual(self.contact.email, 'test@example.com')
        self.assertTrue(self.contact.is_active)
        self.assertFalse(self.contact.unsubscribed)

    def test_contact_str(self):
        self.assertEqual(str(self.contact), 'test@example.com')

    def test_contact_parse_tags(self):
        result = Contact.parse_tags('tag1, tag2, tag3')
        self.assertEqual(result, ['tag1', 'tag2', 'tag3'])

    def test_contact_parse_tags_semicolon(self):
        result = Contact.parse_tags('tag1; tag2')
        self.assertEqual(result, ['tag1', 'tag2'])

    def test_contact_parse_tags_deduplicates(self):
        result = Contact.parse_tags('tag1, tag1')
        self.assertEqual(result, ['tag1'])

    def test_contact_record_bounce(self):
        self.contact.record_bounce()
        self.assertEqual(self.contact.bounce_count, 1)
        self.assertFalse(self.contact.is_suppressed)

    def test_contact_suppress_after_3_bounces(self):
        for _ in range(3):
            self.contact.record_bounce()
        self.assertTrue(self.contact.is_suppressed)

    def test_contact_unsubscribe(self):
        self.contact.unsubscribe()
        self.assertTrue(self.contact.unsubscribed)
        self.assertIsNotNone(self.contact.unsubscribed_at)
        self.assertFalse(self.contact.unsubscribed_from_list)

    def test_contact_unsubscribe_list_level(self):
        self.contact.unsubscribe(list_level=True)
        self.assertTrue(self.contact.unsubscribed_from_list)

    def test_contact_list_get_email_list(self):
        Contact.objects.create(contact_list=self.list, email='active@example.com')
        Contact.objects.create(contact_list=self.list, email='unsub@example.com')
        unsub = Contact.objects.get(email='unsub@example.com')
        unsub.unsubscribe()
        emails = self.list.get_email_list()
        self.assertIn('active@example.com', emails)
        self.assertNotIn('unsub@example.com', emails)

    def test_contact_unique_together(self):
        with self.assertRaises(Exception):
            Contact.objects.create(contact_list=self.list, email='test@example.com')

    def test_contact_list_str(self):
        self.assertEqual(str(self.list), 'Test List')

    def test_contact_tag_creation(self):
        tag = ContactTag.objects.create(user=self.user, name='VIP')
        self.assertEqual(str(tag), 'VIP')

    def test_contact_custom_field_creation(self):
        field = ContactCustomField.objects.create(
            user=self.user, name='Company', field_type='text'
        )
        self.assertEqual(str(field), 'Company')

    def test_custom_field_value_creation(self):
        field = ContactCustomField.objects.create(
            user=self.user, name='Company', field_type='text'
        )
        value = ContactCustomFieldValue.objects.create(
            contact=self.contact, field=field, value='Acme Corp'
        )
        self.assertEqual(str(value), 'Company: Acme Corp')

    def test_segment_creation(self):
        seg = ContactSegment.objects.create(
            user=self.user, name='Test Segment',
            rules=[{'field': 'email', 'operator': 'contains', 'value': 'test'}],
        )
        self.assertEqual(str(seg), 'Test Segment')

    def test_segment_get_matched_contacts(self):
        seg = ContactSegment.objects.create(
            user=self.user, name='Test Segment',
            rules=[{'field': 'email', 'operator': 'contains', 'value': 'example'}],
        )
        matched = seg.get_matched_contacts()
        self.assertIn(self.contact, matched)

    def test_segment_no_rules_returns_none(self):
        seg = ContactSegment.objects.create(
            user=self.user, name='Empty Segment',
        )
        self.assertEqual(seg.get_matched_contacts().count(), 0)

    def test_contact_default_active(self):
        c = Contact.objects.create(contact_list=self.list, email='new@example.com')
        self.assertTrue(c.is_active)

    def test_contact_default_unsubscribed(self):
        c = Contact.objects.create(contact_list=self.list, email='new2@example.com')
        self.assertFalse(c.unsubscribed)

    def test_contact_default_is_suppressed(self):
        c = Contact.objects.create(contact_list=self.list, email='new3@example.com')
        self.assertFalse(c.is_suppressed)

    def test_contact_gdpr_defaults(self):
        c = Contact.objects.create(contact_list=self.list, email='gdpr@example.com')
        self.assertFalse(c.gdpr_consent)
        self.assertIsNone(c.gdpr_consent_at)
        self.assertIsNone(c.gdpr_data_exported_at)

    def test_tag_parse_empty(self):
        self.assertEqual(Contact.parse_tags(''), [])
        self.assertEqual(Contact.parse_tags(None), [])

    def test_tag_parse_mixed_separators(self):
        result = Contact.parse_tags('a,b;c')
        self.assertEqual(result, ['a', 'b', 'c'])


class ContactTenantManagerTest(TestCase):
    """Test workspace scoping via TenantManager."""

    def setUp(self):
        self.user = User.objects.create_user(username='user1', email='user1@test.com', password='pass')
        self.user2 = User.objects.create_user(username='user2', email='user2@test.com', password='pass')
        self.ws1 = Workspace.objects.create(name='Workspace 1', created_by=self.user)
        self.ws2 = Workspace.objects.create(name='Workspace 2', created_by=self.user)
        WorkspaceMembership.objects.create(user=self.user, workspace=self.ws1, role='owner')
        WorkspaceMembership.objects.create(user=self.user, workspace=self.ws2, role='owner')

        # Create data in ws1
        with tenant_context(self.ws1):
            self.list1 = ContactList.objects.create(
                user=self.user, workspace=self.ws1, name='WS1 List'
            )
            self.tag1 = ContactTag.objects.create(
                user=self.user, workspace=self.ws1, name='WS1 Tag'
            )
            self.contact1 = Contact.objects.create(
                contact_list=self.list1, email='ws1@example.com'
            )

        # Create data in ws2
        with tenant_context(self.ws2):
            self.list2 = ContactList.objects.create(
                user=self.user, workspace=self.ws2, name='WS2 List'
            )
            self.tag2 = ContactTag.objects.create(
                user=self.user, workspace=self.ws2, name='WS2 Tag'
            )
            self.contact2 = Contact.objects.create(
                contact_list=self.list2, email='ws2@example.com'
            )

        # Create personal data (no workspace)
        self.personal_list = ContactList.objects.create(
            user=self.user, name='Personal List'
        )
        self.personal_tag = ContactTag.objects.create(
            user=self.user, name='Personal Tag'
        )
        self.personal_contact = Contact.objects.create(
            contact_list=self.personal_list, email='personal@example.com'
        )

    def tearDown(self):
        clear_current_tenant()

    def test_contactlist_scoped_to_ws1(self):
        with tenant_context(self.ws1):
            qs = list(ContactList.objects.all())
            self.assertIn(self.list1, qs)
            self.assertNotIn(self.list2, qs)
            self.assertNotIn(self.personal_list, qs)

    def test_contactlist_scoped_to_ws2(self):
        with tenant_context(self.ws2):
            qs = list(ContactList.objects.all())
            self.assertIn(self.list2, qs)
            self.assertNotIn(self.list1, qs)
            self.assertNotIn(self.personal_list, qs)

    def test_contactlist_personal_mode(self):
        """Personal mode: TenantManager returns all. View-level filter_by_context handles scoping."""
        qs = list(ContactList.objects.all())
        self.assertIn(self.personal_list, qs)
        self.assertIn(self.list1, qs)
        self.assertIn(self.list2, qs)

    def test_contact_scoped_to_ws1(self):
        with tenant_context(self.ws1):
            qs = list(Contact.objects.all())
            self.assertIn(self.contact1, qs)
            self.assertNotIn(self.contact2, qs)
            self.assertNotIn(self.personal_contact, qs)

    def test_contact_scoped_to_ws2(self):
        with tenant_context(self.ws2):
            qs = list(Contact.objects.all())
            self.assertIn(self.contact2, qs)
            self.assertNotIn(self.contact1, qs)
            self.assertNotIn(self.personal_contact, qs)

    def test_contact_personal_mode(self):
        """Personal mode: TenantManager applies no filter; Contact has no user field."""
        qs = list(Contact.objects.all())
        self.assertIn(self.personal_contact, qs)
        self.assertIn(self.contact1, qs)
        self.assertIn(self.contact2, qs)

    def test_tag_scoped_to_ws1(self):
        with tenant_context(self.ws1):
            qs = list(ContactTag.objects.all())
            self.assertIn(self.tag1, qs)
            self.assertNotIn(self.tag2, qs)
            self.assertNotIn(self.personal_tag, qs)

    def test_tag_scoped_to_ws2(self):
        with tenant_context(self.ws2):
            qs = list(ContactTag.objects.all())
            self.assertIn(self.tag2, qs)
            self.assertNotIn(self.tag1, qs)
            self.assertNotIn(self.personal_tag, qs)

    def test_tag_personal_mode(self):
        """Personal mode: TenantManager returns all. View-level filter_by_context handles scoping."""
        qs = list(ContactTag.objects.all())
        self.assertIn(self.personal_tag, qs)
        self.assertIn(self.tag1, qs)
        self.assertIn(self.tag2, qs)

    def test_no_workspace_crash_on_contact_query(self):
        """TenantManager should not crash when model has no direct workspace field."""
        with tenant_context(self.ws1):
            count = Contact.objects.count()
            self.assertEqual(count, 1)

    def test_no_workspace_crash_on_custom_field_value(self):
        """TenantManager should not crash on ContactCustomFieldValue."""
        field = ContactCustomField.objects.create(
            user=self.user, workspace=self.ws1, name='Test'
        )
        with tenant_context(self.ws1):
            ContactCustomFieldValue.objects.create(
                contact=self.contact1, field=field, value='v'
            )
            self.assertEqual(ContactCustomFieldValue.objects.count(), 1)

    def test_segment_get_matched_contacts_workspace_scoped(self):
        with tenant_context(self.ws1):
            seg = ContactSegment.objects.create(
                user=self.user, workspace=self.ws1, name='WS1 Seg',
                rules=[{'field': 'email', 'operator': 'contains', 'value': 'ws1'}],
            )
            matched = seg.get_matched_contacts()
            self.assertIn(self.contact1, matched)
            self.assertNotIn(self.contact2, matched)

    def test_segment_get_matched_contacts_personal_mode(self):
        seg = ContactSegment.objects.create(
            user=self.user, name='Personal Seg',
            rules=[{'field': 'email', 'operator': 'contains', 'value': 'personal'}],
        )
        matched = seg.get_matched_contacts()
        self.assertIn(self.personal_contact, matched)
        self.assertNotIn(self.contact1, matched)


class ContactTagUniqueConstraintTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', email='u@test.com', password='p')
        self.ws = Workspace.objects.create(name='WS', created_by=self.user)
        WorkspaceMembership.objects.create(user=self.user, workspace=self.ws, role='owner')

    def test_unique_tag_per_workspace(self):
        ContactTag.objects.create(user=self.user, workspace=self.ws, name='VIP')
        with self.assertRaises(Exception):
            ContactTag.objects.create(user=self.user, workspace=self.ws, name='VIP')

    def test_same_tag_name_different_workspaces(self):
        ws2 = Workspace.objects.create(name='WS2', created_by=self.user)
        ContactTag.objects.create(user=self.user, workspace=self.ws, name='VIP')
        # Should not raise — different workspace
        ContactTag.objects.create(user=self.user, workspace=ws2, name='VIP')

    def test_same_tag_name_personal_mode(self):
        ContactTag.objects.create(user=self.user, name='VIP')
        with self.assertRaises(Exception):
            ContactTag.objects.create(user=self.user, name='VIP')

    def test_same_tag_name_different_users_personal(self):
        user2 = User.objects.create_user(username='u2', email='u2@test.com', password='p')
        ContactTag.objects.create(user=self.user, name='VIP')
        # Should not raise — different user
        ContactTag.objects.create(user=user2, name='VIP')

    def test_unique_custom_field_per_workspace(self):
        ContactCustomField.objects.create(user=self.user, workspace=self.ws, name='Company')
        with self.assertRaises(Exception):
            ContactCustomField.objects.create(user=self.user, workspace=self.ws, name='Company')

    def test_same_custom_field_name_different_workspaces(self):
        ws2 = Workspace.objects.create(name='WS2', created_by=self.user)
        ContactCustomField.objects.create(user=self.user, workspace=self.ws, name='Company')
        ContactCustomField.objects.create(user=self.user, workspace=ws2, name='Company')

    def test_same_custom_field_name_personal_mode(self):
        ContactCustomField.objects.create(user=self.user, name='Company')
        with self.assertRaises(Exception):
            ContactCustomField.objects.create(user=self.user, name='Company')
