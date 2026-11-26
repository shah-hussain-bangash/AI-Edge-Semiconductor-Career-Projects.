"""Read-only, account-scoped software observations; never a release acceptance decision."""
from datetime import datetime,timezone
from fastapi import Request,Response
from maintenance_requests import fresh_actor,require_role,READ_ROLES
import approved_guidance
import operational_models
import operational_notifications
import platform_operations

SCOPE='local-capability-observations'


def snapshot(db,actor):
    def count(table,where='',params=()):return db.execute('SELECT count(*) FROM '+table+where,params).fetchone()[0]
    admin=actor['role'] in ('admin','auditor')
    cases=" WHERE assignee_id=?" if actor['role']=='operator' else ''
    orders=" WHERE creator_id=? OR technician_id=?" if actor['role']=='operator' else ''
    case_args=(actor['id'],) if cases else ()
    order_args=(actor['id'],actor['id']) if orders else ()
    visible_cases=count('operational_cases',cases,case_args)
    visible_orders=count('operational_orders',orders,order_args)
    active_assets=count('operational_assets',' WHERE retired=0')
    runs={source:count('bench_runs',' WHERE source_type=?',(source,)) for source in ('software-fixture','measured-unverified')}
    policies=count('operational_rules');enabled=count('operational_rules',' WHERE enabled=1')
    models=list(db.execute('SELECT * FROM operational_models ORDER BY id LIMIT 100'))
    for model in models:operational_models.artifact(model)
    current_models=sum(operational_models.current(db,row) for row in models)
    sources=[]
    for row in db.execute("SELECT * FROM approved_guidance_documents WHERE state='approved' LIMIT 500"):
        if approved_guidance.can_read(row,actor) and approved_guidance.reviewer_active(db,row):
            approved_guidance.present(row,actor);sources.append(row['id'])
    if actor['role']=='operator':
        evidence=count('operational_evidence',""" WHERE (kind='case' AND record_id IN
            (SELECT id FROM operational_cases WHERE assignee_id=?)) OR (kind='order' AND record_id IN
            (SELECT id FROM operational_orders WHERE creator_id=? OR technician_id=?))""",(actor['id'],actor['id'],actor['id']))
    else:evidence=count('operational_evidence')
    mfa=db.execute('SELECT enabled FROM account_mfa WHERE user_id=?',(actor['id'],)).fetchone()
    email=operational_notifications.config(db)
    items=[]
    def add(identity,title,state,observation,next_step,workspace):
        items.append(dict(id=identity,title=title,software='Available locally',state=state,observation=observation,next_step=next_step,workspace=workspace,production_accepted=False))
    add('registered-data','Registered data workspace','records_needed' if not sum(runs.values()) else 'review_required',
        f"{active_assets} active mappings; {runs['software-fixture']} fixture runs; {runs['measured-unverified']} gateway-declared measurement runs (unverified).",
        'Review exact source mappings, channel validity and retained run provenance. A stored reading does not verify calibration or a connected cable.','telemetry')
    add('asset-lifecycle','Asset and policy lifecycle','configuration_needed' if not active_assets else 'available_locally',
        f'{active_assets} active mappings; {policies} saved policies; {enabled} policies marked enabled.',
        'Register the exact device/source lane and deliberately review policy thresholds. Stored enable flags do not establish current policy authority.','assets')
    add('threshold-cases','Threshold review cases','records_needed' if not visible_cases else 'review_required',
        f'{visible_cases} cases visible to this account.',
        'Review original inputs and source labels. Threshold crossings are not fault diagnoses.','alerts')
    reviewers=count('users'," WHERE disabled=0 AND role='admin'") if admin else None
    add('maintenance','Case-linked maintenance','configuration_needed' if admin and reviewers<2 else 'records_needed' if not visible_orders else 'review_required',
        f'{visible_orders} work records visible to this account.'+(' Independent administrator review needs a second active administrator.' if admin and reviewers<2 else ''),
        'Use independent approval and closure review with retained evidence. A closed record does not certify physical work.','maintenance')
    add('notifications','Inbox and optional email','configuration_needed' if not email['provider_configured'] else 'review_required',
        f"{count('operational_notifications',' WHERE user_id=?',(actor['id'],))} notices addressed to this account. Email service: "+('configured' if email['provider_configured'] else 'not configured')+'; delivery policy: '+('enabled' if email['enabled'] else 'disabled')+'.',
        'Review recipients and delayed notices before enabling a privately configured service. Fixture notices remain local. Run the separate worker explicitly.','settings')
    add('studies','Statistical baseline studies','records_needed' if not models else 'review_required',
        f'{len(models)} retained baseline studies.',
        'Use independent retained runs and review training/validation/holdout evidence. Failure accuracy and remaining useful life are not established.','models')
    add('scoring','Runtime baseline scoring','configuration_needed' if not current_models else 'review_required',
        f'{current_models} baseline releases with current local authority; {count("operational_scores")} retained scores.',
        'Independently review the exact artifact and matching source. A deviation score is not a qualified failure prediction.','models')
    add('guidance','Approved-source guidance','records_needed' if not sources else 'available_locally',
        f'{len(sources)} currently approved sources accessible to this account.',
        'Review source rights and independent approvals. Search returns cited excerpts or abstains; no external language-model service is connected.','knowledge')
    add('identity','Local account protection','available_locally' if mfa and mfa['enabled'] else 'optional_setup',
        'Email/password sign-in is active for this session. Your authenticator: '+('enabled' if mfa and mfa['enabled'] else 'not enabled')+'.',
        'Optional authenticator enrollment needs a private server key and retained recovery codes. Company sign-in and remote password recovery remain unconfigured.','settings')
    add('evidence','Private evidence files','records_needed' if not evidence else 'review_required',
        f'{evidence} private evidence files accessible to this account; content is not malware scanned.',
        'Review provenance and file safety separately. Retained files and hashes do not establish physical acceptance.','alerts')
    worker=db.execute('SELECT last_pass FROM platform_worker_status WHERE singleton=1').fetchone() if admin else None
    add('observability','Service and worker observations','access_restricted' if not admin else 'review_required',
        ('Worker heartbeat recorded; inspect age and result in Settings.' if worker else 'No platform worker heartbeat recorded.') if admin else 'Detailed service observations require an administrator or auditor.',
        'Inspect current database checks, metrics and worker results. No external uptime service or service-level acceptance is connected.','settings')
    add('releases','Reviewed source and local controls','review_required',
        'Source packaging and managed local start/status/graceful-stop tools are implemented. This check builds or deploys nothing.',
        'Verify the exact source package and backup before updating. Hosting remains deferred; no online deployment is inferred.','settings')
    if admin:
        ready=platform_operations.backup_ready()
        backup_state='configuration_needed' if not all(ready[key] for key in ('private_key_ready','output_directory_ready')) else 'review_required'
        completed=count('platform_backup_jobs'," WHERE state='completed'")
        backup_text=f"Private key: {'configured' if ready['private_key_ready'] else 'not configured'}; backup directory: {'configured' if ready['output_directory_ready'] else 'not configured'}; completed jobs: {completed}."
    else:backup_state='access_restricted';backup_text='Private recovery configuration requires an administrator or auditor.'
    add('recovery','Protected recovery',backup_state,backup_text,
        'Configure private storage and run the explicit worker. Perform an independently reviewed off-machine restore drill; queued or completed jobs alone do not prove recovery objectives.','settings')
    add('governance','Reviewed retention and governance','review_required' if admin else 'access_restricted',
        f'{count("platform_retention_plans")} retained deletion plans; applying a plan requires independent review.' if admin else 'Retention plans require an administrator or auditor.',
        'Review exact deletion targets, source rights and scope. Backup copies and broader retention obligations remain separate.','settings')
    assert len(items)==14
    return dict(scope=SCOPE,generated_at=datetime.now(timezone.utc).isoformat(),role=actor['role'],items=items,
        production_ready=False,equipment_authorized=False,physical_acceptance_verified=False,acceptance_records_changed=False,
        basis='Current local database snapshot and configuration presence; saved counts are not proof of acceptance. No hardware or provider connection is tested.')


def install_routes(app,database,require_user):
    @app.get('/api/production-readiness/local-capabilities')
    def capabilities(request:Request,response:Response):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            return snapshot(db,actor)
