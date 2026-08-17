-- 投资公司法务风控独立数据域（MySQL 8.0+）。
-- 先执行 20260814_legal_risk_foundation.sql，再执行本文件。

CREATE TABLE IF NOT EXISTS legal_case_sequence (
    year INT NOT NULL PRIMARY KEY,
    current_value INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    stage VARCHAR(32) NOT NULL DEFAULT 'draft',
    case_no VARCHAR(32) NULL,
    case_name VARCHAR(255) NOT NULL,
    cause_of_action VARCHAR(255) NOT NULL DEFAULT '',
    court VARCHAR(255) NOT NULL DEFAULT '',
    court_case_no VARCHAR(128) NOT NULL DEFAULT '',
    subject_amount DECIMAL(18,2) NOT NULL DEFAULT 0,
    status VARCHAR(32) NULL,
    responsible_user_id INT NULL,
    confidentiality_level VARCHAR(32) NOT NULL DEFAULT 'internal',
    law_firm VARCHAR(255) NOT NULL DEFAULT '',
    attorney_name VARCHAR(128) NOT NULL DEFAULT '',
    case_summary TEXT NOT NULL,
    claims TEXT NOT NULL,
    enforcement_property_status TEXT NOT NULL,
    terminal_date DATE NULL,
    closed_date DATE NULL,
    closure_summary TEXT NOT NULL,
    archived_at DATETIME NULL,
    archive_note TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    activated_by INT NULL,
    activated_at DATETIME NULL,
    created_by INT NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_case_no (case_no),
    KEY ix_legal_case_stage (stage),
    KEY ix_legal_case_status (status),
    KEY ix_legal_case_court_case_no (court_case_no),
    KEY ix_legal_case_responsible (responsible_user_id),
    KEY ix_legal_case_deleted (deleted_at),
    CONSTRAINT fk_legal_case_responsible FOREIGN KEY (responsible_user_id) REFERENCES sys_user(id) ON DELETE SET NULL,
    CONSTRAINT fk_legal_case_activated_by FOREIGN KEY (activated_by) REFERENCES sys_user(id),
    CONSTRAINT fk_legal_case_created_by FOREIGN KEY (created_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_party (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    party_type VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    identity_type VARCHAR(32) NOT NULL DEFAULT 'organization',
    identity_no VARCHAR(64) NOT NULL DEFAULT '',
    contact VARCHAR(128) NOT NULL DEFAULT '',
    address VARCHAR(500) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_party_case (case_id),
    CONSTRAINT fk_legal_party_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_collaborator (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    user_id INT NOT NULL,
    collaborator_type VARCHAR(32) NOT NULL,
    effective_at DATETIME NOT NULL,
    expires_at DATETIME NULL,
    assigned_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_case_collaborator (case_id, user_id, collaborator_type),
    CONSTRAINT fk_legal_collaborator_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_collaborator_user FOREIGN KEY (user_id) REFERENCES sys_user(id),
    CONSTRAINT fk_legal_collaborator_assigner FOREIGN KEY (assigned_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_judgment (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    judgment_type VARCHAR(32) NOT NULL,
    summary TEXT NOT NULL,
    judgment_date DATE NULL,
    effective_date DATE NULL,
    performance_deadline DATE NULL,
    executable_amount DECIMAL(18,2) NULL,
    is_current_enforcement_basis TINYINT(1) NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_judgment_case (case_id),
    KEY ix_legal_judgment_deadline (performance_deadline),
    CONSTRAINT fk_legal_judgment_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_asset (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    asset_type VARCHAR(64) NOT NULL,
    asset_name VARCHAR(500) NOT NULL,
    measure_type VARCHAR(64) NOT NULL,
    priority_type VARCHAR(32) NOT NULL DEFAULT '',
    start_date DATE NULL,
    expiry_date DATE NULL,
    reminder_days INT NULL,
    disposal_status VARCHAR(64) NOT NULL DEFAULT '',
    notes TEXT NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_asset_case (case_id),
    KEY ix_legal_asset_expiry (expiry_date),
    CONSTRAINT fk_legal_asset_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_recovery (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    recovery_type VARCHAR(32) NOT NULL,
    recovery_date DATE NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    source_description TEXT NOT NULL,
    registered_by INT NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_recovery_case (case_id),
    CONSTRAINT fk_legal_recovery_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_recovery_user FOREIGN KEY (registered_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_progress (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    progress_type VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    risk_points TEXT NOT NULL,
    next_plan TEXT NOT NULL,
    responsible_user_id INT NULL,
    planned_date DATE NULL,
    registered_by INT NOT NULL,
    recorded_at DATETIME NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_progress_case (case_id),
    CONSTRAINT fk_legal_progress_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_progress_responsible FOREIGN KEY (responsible_user_id) REFERENCES sys_user(id),
    CONSTRAINT fk_legal_progress_user FOREIGN KEY (registered_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_deadline (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    deadline_type VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    event_date DATE NOT NULL,
    reminder_days INT NULL,
    responsible_user_id INT NULL,
    is_completed TINYINT(1) NOT NULL DEFAULT 0,
    completed_at DATETIME NULL,
    completion_note TEXT NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_deadline_case (case_id),
    KEY ix_legal_deadline_event (event_date),
    CONSTRAINT fk_legal_deadline_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_deadline_responsible FOREIGN KEY (responsible_user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_attachment (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    related_type VARCHAR(32) NOT NULL,
    related_id BIGINT NULL,
    category VARCHAR(64) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    storage_name VARCHAR(255) NOT NULL,
    extension VARCHAR(16) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    uploaded_by INT NOT NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_attachment_storage (storage_name),
    KEY ix_legal_attachment_case (case_id),
    KEY ix_legal_attachment_sha256 (sha256),
    CONSTRAINT fk_legal_attachment_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_attachment_user FOREIGN KEY (uploaded_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_alert (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    source_id BIGINT NOT NULL,
    alert_type VARCHAR(32) NOT NULL,
    cycle_key VARCHAR(64) NOT NULL,
    trigger_date DATE NOT NULL,
    due_date DATE NOT NULL,
    level VARCHAR(16) NOT NULL DEFAULT 'normal',
    responsible_user_id INT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    result TEXT NOT NULL,
    completed_at DATETIME NULL,
    closed_reason TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_case_alert_cycle (case_id, source_type, source_id, alert_type, cycle_key),
    KEY ix_legal_alert_due (due_date),
    KEY ix_legal_alert_status (status),
    CONSTRAINT fk_legal_alert_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_alert_responsible FOREIGN KEY (responsible_user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_alert_delivery (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    alert_id BIGINT NOT NULL,
    channel VARCHAR(16) NOT NULL,
    stage_key VARCHAR(32) NOT NULL,
    recipient_scope VARCHAR(64) NOT NULL DEFAULT 'legal_group',
    attempts INT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    claim_token VARCHAR(64) NULL,
    claim_expires_at DATETIME NULL,
    response_summary VARCHAR(500) NOT NULL DEFAULT '',
    failure_reason TEXT NOT NULL,
    first_sent_at DATETIME NULL,
    last_sent_at DATETIME NULL,
    next_retry_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_alert_delivery_stage (alert_id, channel, stage_key, recipient_scope),
    KEY ix_legal_delivery_retry (status, next_retry_at),
    KEY ix_legal_delivery_claim (claim_token, claim_expires_at),
    CONSTRAINT fk_legal_delivery_alert FOREIGN KEY (alert_id) REFERENCES legal_case_alert(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_activity (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    action VARCHAR(64) NOT NULL,
    object_type VARCHAR(32) NOT NULL,
    object_id BIGINT NULL,
    change_summary TEXT NOT NULL,
    actor_id INT NOT NULL,
    actor_name VARCHAR(64) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_activity_case (case_id, created_at),
    CONSTRAINT fk_legal_activity_case FOREIGN KEY (case_id) REFERENCES legal_case(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_activity_actor FOREIGN KEY (actor_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_import_batch (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_hash CHAR(64) NOT NULL,
    template_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'previewed',
    total_rows INT NOT NULL DEFAULT 0,
    importable_rows INT NOT NULL DEFAULT 0,
    warning_rows INT NOT NULL DEFAULT 0,
    error_rows INT NOT NULL DEFAULT 0,
    created_by INT NOT NULL,
    confirmed_by INT NULL,
    confirmed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_legal_import_batch_status (status),
    CONSTRAINT fk_legal_import_batch_creator FOREIGN KEY (created_by) REFERENCES sys_user(id),
    CONSTRAINT fk_legal_import_batch_confirmer FOREIGN KEY (confirmed_by) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS legal_case_import_row (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    sheet_name VARCHAR(64) NOT NULL,
    row_number INT NOT NULL,
    normalized_data JSON NOT NULL,
    validation_status VARCHAR(16) NOT NULL,
    warnings JSON NOT NULL,
    errors JSON NOT NULL,
    imported_case_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_legal_import_row (batch_id, sheet_name, row_number),
    KEY ix_legal_import_row_status (validation_status),
    CONSTRAINT fk_legal_import_row_batch FOREIGN KEY (batch_id) REFERENCES legal_case_import_batch(id) ON DELETE CASCADE,
    CONSTRAINT fk_legal_import_row_case FOREIGN KEY (imported_case_id) REFERENCES legal_case(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
