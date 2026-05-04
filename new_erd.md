`mermaid
erDiagram
  CustomUser {
    uuid id PK
    string email
    string first_name
    string last_name
    string role
    string phone
    string bio
    string avatar
    string billing_email
    string plan_type
    string status
    boolean is_verified
    uuid last_active_workspace
    datetime created_at
    datetime updated_at
  }
  BackupJob {
    uuid id PK
    uuid workspace FK
    string backup_type
    string status
    boolean include_files
    boolean encryption_enabled
    string file_url
    int file_size
    uuid created_by FK
    datetime created_at
    datetime completed_at
    string error_message
  }
  Workspace ||--o{ BackupJob : "workspace"
  User ||--o{ BackupJob : "created_by"
  ExportJob {
    uuid id PK
    uuid workspace FK
    string export_type
    string format
    string status
    json date_range
    string file_url
    int file_size
    uuid created_by FK
    datetime created_at
    datetime completed_at
    string error_message
  }
  Workspace ||--o{ ExportJob : "workspace"
  User ||--o{ ExportJob : "created_by"
  DailyCheckIn {
    uuid id PK
    uuid workspace FK
    uuid user FK
    string sentiment
    string yesterday_progress
    string tomorrow_plan
    boolean has_blockers
    uuid yesterday_tasks FK
    uuid tomorrow_tasks FK
    date date
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ DailyCheckIn : "workspace"
  User ||--o{ DailyCheckIn : "user"
  Task }o--o{ DailyCheckIn : "yesterday_tasks"
  Task }o--o{ DailyCheckIn : "tomorrow_tasks"
  CheckInBlocker {
    uuid id PK
    uuid checkin FK
    string description
    uuid notify_member FK
    string priority
    datetime created_at
  }
  DailyCheckIn ||--o{ CheckInBlocker : "checkin"
  User ||--o{ CheckInBlocker : "notify_member"
  Folder {
    uuid id PK
    uuid workspace FK
    string name
    uuid parent FK
    uuid created_by FK
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ Folder : "workspace"
  Folder ||--o{ Folder : "parent"
  User ||--o{ Folder : "created_by"
  File {
    uuid id PK
    uuid workspace FK
    uuid folder FK
    string file
    string file_name
    string file_type
    int file_size
    uuid uploaded_by FK
    datetime uploaded_at
  }
  Workspace ||--o{ File : "workspace"
  Folder ||--o{ File : "folder"
  User ||--o{ File : "uploaded_by"
  Integration {
    uuid id PK
    uuid workspace FK
    string name
    string icon
    string url
    string category
    string description
    uuid created_by FK
    datetime created_at
    datetime updated_at
    boolean is_visible
  }
  Workspace ||--o{ Integration : "workspace"
  User ||--o{ Integration : "created_by"
  WorkspaceLog {
    uuid id PK
    uuid workspace FK
    uuid user FK
    string log_type
    string severity
    string action
    string entity_type
    uuid entity_id
    string description
    json metadata
    string ip_address
    string user_agent
    datetime created_at
  }
  Workspace ||--o{ WorkspaceLog : "workspace"
  User ||--o{ WorkspaceLog : "user"
  AuditTrailLog {
    uuid id PK
    uuid workspace FK
    uuid user FK
    string action
    string entity_type
    uuid entity_id
    json old_values
    json new_values
    string ip_address
    string user_agent
    string session_id
    datetime created_at
  }
  Workspace ||--o{ AuditTrailLog : "workspace"
  User ||--o{ AuditTrailLog : "user"
  UserActivityLog {
    uuid id PK
    uuid user FK
    uuid workspace FK
    string activity_type
    string module
    string endpoint
    int duration_ms
    string ip_address
    string user_agent
    string session_id
    json metadata
    datetime created_at
  }
  User ||--o{ UserActivityLog : "user"
  Workspace ||--o{ UserActivityLog : "workspace"
  SystemEventLog {
    uuid id PK
    uuid workspace FK
    string event_type
    string severity
    string message
    string source
    string error_code
    string stack_trace
    json metadata
    boolean resolved
    datetime resolved_at
    datetime created_at
  }
  Workspace ||--o{ SystemEventLog : "workspace"
  ModuleAccess {
    uuid id PK
    uuid user FK
    uuid workspace FK
    string module_name
    int session_duration
    json actions_performed
    string ip_address
    string user_agent
    datetime accessed_at
  }
  User ||--o{ ModuleAccess : "user"
  Workspace ||--o{ ModuleAccess : "workspace"
  ModulePreferences {
    uuid id PK
    uuid user FK
    json favorite_modules
    json module_order
    boolean quick_access_enabled
    datetime created_at
    datetime updated_at
  }
  User ||--|| ModulePreferences : "user"
  SystemMetric {
    uuid id PK
    string metric_type
    string metric_name
    float value
    string unit
    json metadata
    datetime timestamp
  }
  SystemAlert {
    uuid id PK
    string alert_type
    string severity
    string status
    string title
    string description
    json metadata
    datetime created_at
    datetime resolved_at
  }
  UsageMetric {
    uuid id PK
    uuid organization FK
    string metric_name
    float value
    string unit
    float cost
    date date
    json metadata
  }
  Organization ||--o{ UsageMetric : "organization"
  Notification {
    uuid id PK
    uuid user FK
    uuid triggered_by FK
    uuid workspace FK
    string action
    string description
    string note_type
    string severity
    boolean is_read
    datetime created_at
    datetime read_at
  }
  User ||--o{ Notification : "user"
  User ||--o{ Notification : "triggered_by"
  Workspace ||--o{ Notification : "workspace"
  Organization {
    uuid id PK
    string name
    uuid owner FK
    uuid members FK
    string plan_type
    string status
    string billing_email
    datetime created_at
    datetime updated_at
    boolean is_active
  }
  User ||--o{ Organization : "owner"
  User }o--o{ Organization : "members"
  OrganizationMembership {
    uuid id PK
    uuid organization FK
    uuid user FK
    string role
    datetime joined_at
    boolean is_active
  }
  Organization ||--o{ OrganizationMembership : "organization"
  User ||--o{ OrganizationMembership : "user"
  OrganizationUsage {
    uuid id PK
    uuid organization FK
    int user_count
    int workspace_count
    int storage_used_mb
    int file_count
    datetime last_calculated
  }
  Organization ||--|| OrganizationUsage : "organization"
  OrganizationInvitation {
    uuid id PK
    uuid organization FK
    string email
    uuid invited_by FK
    string role
    string status
    string token
    datetime created_at
    datetime expires_at
  }
  Organization ||--o{ OrganizationInvitation : "organization"
  User ||--o{ OrganizationInvitation : "invited_by"
  QuickLinkCategory {
    uuid id PK
    string name
    uuid user FK
    datetime created_at
  }
  User ||--o{ QuickLinkCategory : "user"
  QuickLink {
    uuid id PK
    uuid user FK
    string title
    string url
    string icon
    string category
    uuid workspace FK
    string entity_type
    string entity_id
    boolean is_pinned
    int sort_order
    datetime created_at
    datetime updated_at
  }
  User ||--o{ QuickLink : "user"
  Workspace ||--o{ QuickLink : "workspace"
  SharedQuickLink {
    uuid id PK
    uuid workspace FK
    string title
    string url
    string description
    string icon
    string category
    string visibility
    uuid created_by FK
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ SharedQuickLink : "workspace"
  User ||--o{ SharedQuickLink : "created_by"
  RecentItem {
    uuid id PK
    uuid user FK
    string item_type
    string item_id
    uuid workspace FK
    string action
    int access_count
    datetime last_accessed
    datetime created_at
  }
  User ||--o{ RecentItem : "user"
  Workspace ||--o{ RecentItem : "workspace"
  Report {
    uuid id PK
    uuid workspace FK
    uuid user FK
    string report_type
    string title
    string description
    string status
    string format
    json parameters
    json data
    string file_url
    string job_id
    uuid created_by FK
    datetime created_at
    datetime updated_at
    datetime completed_at
    datetime expires_at
  }
  Workspace ||--o{ Report : "workspace"
  User ||--o{ Report : "user"
  User ||--o{ Report : "created_by"
  ReportTemplate {
    uuid id PK
    string name
    string report_type
    string category
    string description
    json template_config
    boolean is_active
    datetime created_at
  }
  ScheduledReport {
    uuid id PK
    uuid workspace FK
    string report_type
    string frequency
    json recipients
    json parameters
    datetime next_run
    datetime last_run
    boolean is_active
    uuid created_by FK
    datetime created_at
  }
  Workspace ||--o{ ScheduledReport : "workspace"
  User ||--o{ ScheduledReport : "created_by"
  SharedReport {
    uuid id PK
    uuid report FK
    uuid shared_by FK
    json recipients
    string access_level
    string message
    string share_token
    datetime expires_at
    datetime created_at
  }
  Report ||--o{ SharedReport : "report"
  User ||--o{ SharedReport : "shared_by"
  Subscription {
    uuid id PK
    uuid organization FK
    string plan_type
    string billing_cycle
    string status
    datetime start_date
    datetime end_date
    datetime grace_period_end
    string payment_provider
    string subscription_code
    string email_token
    datetime created_at
    datetime updated_at
    string authorization_code
    string billing_email
    string email_token
    boolean is_in_grace_period
    int retry_count
    datetime next_retry_date
    boolean cancel_at_period_end
    string next_plan_type
    datetime last_charged_date
    datetime next_billing_date
  }
  Organization ||--|| Subscription : "organization"
  PaymentHistory {
    uuid id PK
    uuid organization FK
    float amount
    string currency
    string payment_provider
    string reference
    string status
    string plan_type
    string billing_cycle
    datetime transaction_date
    json metadata
  }
  Organization ||--o{ PaymentHistory : "organization"
  PaymentMethod {
    uuid id PK
    uuid organization FK
    string provider
    string card_last4
    string card_type
    string card_expiry
    string card_first6
    boolean is_default
    datetime created_at
    datetime updated_at
  }
  Organization ||--o{ PaymentMethod : "organization"
  Task {
    uuid id PK
    uuid workspace FK
    string task_name
    string task_description
    uuid assigned_to FK
    uuid created_by FK
    string status
    string priority
    datetime start_date
    datetime end_date
    string duration
    int milestone
    int sprint
    int percent_complete
    boolean has_blocker
    string blocker_reason
    int ticket_number
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ Task : "workspace"
  User ||--o{ Task : "assigned_to"
  User ||--o{ Task : "created_by"
  TaskComment {
    uuid id PK
    uuid task FK
    uuid user FK
    string comment_text
    uuid parent_comment FK
    datetime created_at
    datetime updated_at
  }
  Task ||--o{ TaskComment : "task"
  User ||--o{ TaskComment : "user"
  TaskComment ||--o{ TaskComment : "parent_comment"
  TaskCommentAttachment {
    uuid id PK
    uuid comment FK
    string file
    string file_url
    string file_name
    int file_size
    uuid uploaded_by FK
    datetime uploaded_at
  }
  TaskComment ||--o{ TaskCommentAttachment : "comment"
  User ||--o{ TaskCommentAttachment : "uploaded_by"
  TaskAttachment {
    uuid id PK
    uuid task FK
    string file
    string file_url
    string file_name
    int file_size
    uuid uploaded_by FK
    datetime uploaded_at
  }
  Task ||--o{ TaskAttachment : "task"
  User ||--o{ TaskAttachment : "uploaded_by"
  PersonalTask {
    uuid id PK
    uuid user FK
    string title
    datetime deadline
    boolean completed
    datetime created_at
    datetime updated_at
  }
  User ||--o{ PersonalTask : "user"
  WaitlistEntry {
    uuid id PK
    string email
    datetime created_at
  }
  DashboardWidget {
    uuid id PK
    uuid user FK
    string widget_type
    string title
    int position_x
    int position_y
    int width
    int height
    boolean is_visible
    json config
    datetime created_at
    datetime updated_at
  }
  CustomUser ||--o{ DashboardWidget : "user"
  WidgetLayout {
    uuid id PK
    uuid user FK
    json layout_config
    int columns
    datetime created_at
    datetime updated_at
  }
  CustomUser ||--|| WidgetLayout : "user"
  WikiDocument {
    uuid id PK
    uuid workspace FK
    string document_title
    string document_description
    string category
    string visibility
    string image
    uuid author FK
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ WikiDocument : "workspace"
  User ||--o{ WikiDocument : "author"
  WikiDocumentAttachment {
    uuid id PK
    uuid document FK
    string file
    string file_url
    string file_name
    int file_size
    uuid uploaded_by FK
    datetime uploaded_at
  }
  WikiDocument ||--o{ WikiDocumentAttachment : "document"
  User ||--o{ WikiDocumentAttachment : "uploaded_by"
  Workspace {
    uuid id PK
    string name
    string description
    string type
    string status
    uuid owner FK
    uuid organization FK
    datetime created_at
    datetime updated_at
    int no_of_tickets
  }
  User ||--o{ Workspace : "owner"
  Organization ||--o{ Workspace : "organization"
  WorkspaceMember {
    uuid id PK
    uuid workspace FK
    uuid user FK
    string name
    string phone
    string job_role
    string role
    string user_status
    datetime joined_at
    string email
  }
  Workspace ||--o{ WorkspaceMember : "workspace"
  User ||--o{ WorkspaceMember : "user"
  WorkspaceInvitation {
    uuid id PK
    uuid workspace FK
    uuid invited_by FK
    string email
    string phone
    string job_role
    string role
    string status
    string user_status
    string token
    datetime expires_at
    datetime created_at
    datetime updated_at
  }
  Workspace ||--o{ WorkspaceInvitation : "workspace"
  User ||--o{ WorkspaceInvitation : "invited_by"
  WorkspaceSettings {
    uuid id PK
    uuid workspace FK
    string timezone
    string date_format
    boolean notifications_enabled
    boolean auto_assign_tasks
    string default_task_priority
    json enabled_modules
    datetime created_at
    datetime updated_at
  }
  Workspace ||--|| WorkspaceSettings : "workspace"
`
