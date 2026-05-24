"""
Management command to import sales leads from the Excel file.
Usage: python manage.py import_leads /path/to/ScaleForge_BuildTracker_Sales_Kit.xlsx
"""
import openpyxl
from django.core.management.base import BaseCommand
from admin_dashboard.models import SalesLead


def _parse_priority(raw):
    if not raw:
        return 'B'
    s = str(raw).strip()
    if 'A' in s:
        return 'A'
    if 'B' in s:
        return 'B'
    return 'C'


STATUS_MAP = {
    'Not Contacted': 'not_contacted',
    'DM Sent': 'dm_sent',
    'Replied': 'replied',
    'Call Booked': 'call_booked',
    'Demo Done': 'demo_done',
    'Converted': 'converted',
    'Not Interested': 'not_interested',
    'No Response': 'no_response',
}


class Command(BaseCommand):
    help = 'Import sales leads from ScaleForge_BuildTracker_Sales_Kit.xlsx'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Path to the Excel file')
        parser.add_argument('--clear', action='store_true', help='Clear existing records before import')

    def handle(self, *args, **options):
        filepath = options['filepath']
        if options['clear']:
            SalesLead.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared all existing leads.'))

        wb = openpyxl.load_workbook(filepath)
        ws = wb['BuildTracker Leads']

        # Row 1 is the header:
        # #, Priority, Company, Website, Sector, Stage, City,
        # Target Title on LinkedIn, LinkedIn Search URL,
        # Why BuildTracker (Pain Angle), LinkedIn DM, Status,
        # Date Contacted, Follow-up Date, Notes

        created = 0
        skipped = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[2]:  # no company name
                skipped += 1
                continue

            status_raw = str(row[11]).strip() if row[11] else 'Not Contacted'
            date_contacted = row[12] if isinstance(row[12], (type(None),)) is False and row[12] else None
            follow_up_date = row[13] if isinstance(row[13], (type(None),)) is False and row[13] else None

            # openpyxl returns datetime for date cells — convert safely
            from datetime import date, datetime
            if isinstance(date_contacted, datetime):
                date_contacted = date_contacted.date()
            elif not isinstance(date_contacted, date):
                date_contacted = None

            if isinstance(follow_up_date, datetime):
                follow_up_date = follow_up_date.date()
            elif not isinstance(follow_up_date, date):
                follow_up_date = None

            SalesLead.objects.create(
                priority=_parse_priority(row[1]),
                company=str(row[2]).strip(),
                website=str(row[3] or '').strip(),
                sector=str(row[4] or '').strip(),
                stage=str(row[5] or '').strip(),
                city=str(row[6] or '').strip(),
                target_title=str(row[7] or '').strip(),
                linkedin_search_url=str(row[8] or '').strip(),
                pain_angle=str(row[9] or '').strip(),
                dm_template=str(row[10] or '').strip(),
                status=STATUS_MAP.get(status_raw, 'not_contacted'),
                date_contacted=date_contacted,
                follow_up_date=follow_up_date,
                notes=str(row[14] or '').strip(),
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Imported {created} leads. Skipped {skipped} empty rows.'
        ))
