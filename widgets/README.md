# Dashboard Widgets Module

## Overview
Complete dashboard widgets system for BuildTracker with customizable layouts and real-time data.

## Features
- User-specific dashboard widget configuration
- 10 widget types (task summary, recent tasks, team performance, etc.)
- Customizable widget layout (position, size, visibility)
- Workspace-specific widget data with date filtering
- Real-time data refresh with configurable intervals

## API Endpoints

### 1. GET /api/users/:userId/dashboard/widgets
Get all widgets and layout for user dashboard
- **Auth**: Required
- **Response**: widgets[], layout, available_widgets[]

### 2. PUT /api/users/:userId/dashboard/widgets
Update widgets and layout for user dashboard
- **Auth**: Required
- **Body**: { widgets[], layout }
- **Response**: { widgets[], layout }

### 3. GET /api/workspaces/:workspaceId/dashboard/widgets/data/:widgetType
Get data for specific widget type
- **Auth**: Required
- **Query**: DateFrom, DateTo
- **Response**: { widget_data, last_updated, refresh_interval }

## Widget Types
1. **task_summary** - Task counts by status
2. **recent_tasks** - Recently created/updated tasks
3. **team_performance** - Member performance metrics
4. **milestone_progress** - Milestone completion tracking
5. **sprint_burndown** - Sprint burndown data
6. **priority_distribution** - Tasks by priority
7. **status_chart** - Visual status breakdown
8. **overdue_tasks** - Overdue task list
9. **completion_trend** - 30-day completion trend
10. **velocity_chart** - Sprint velocity tracking

## Models

### DashboardWidget
- id (UUID)
- user (FK to CustomUser)
- widget_type (choice field)
- title, position_x, position_y, width, height
- is_visible, config (JSON)
- timestamps

### WidgetLayout
- id (UUID)
- user (OneToOne to CustomUser)
- layout_config (JSON)
- columns (default 12)
- timestamps

## Installation
1. App already added to INSTALLED_APPS
2. URLs already configured
3. Run migrations: `python manage.py makemigrations widgets && python manage.py migrate`

## Usage Example
```python
# Get user widgets
GET /api/users/{userId}/dashboard/widgets

# Update layout
PUT /api/users/{userId}/dashboard/widgets
{
  "widgets": [
    {
      "widget_type": "task_summary",
      "title": "My Tasks",
      "position_x": 0,
      "position_y": 0,
      "width": 4,
      "height": 3,
      "is_visible": true,
      "config": {}
    }
  ],
  "layout": {
    "layout_config": {},
    "columns": 12
  }
}

# Get widget data
GET /api/workspaces/{workspaceId}/dashboard/widgets/data/task_summary?DateFrom=2024-01-01&DateTo=2024-12-31
```
