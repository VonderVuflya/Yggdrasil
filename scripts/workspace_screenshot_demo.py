#!/usr/bin/env python3
"""Read-only screenshot fixture. All projects, records and job logs are fictional.

Run from the repository after building web/: python3 scripts/workspace_screenshot_demo.py
Uses a fresh temporary YGG_HOME/database, no user sources or external services.
Only query routes are enabled; operation logs are explicitly synthetic fixtures.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ygg-readme-demo-') as temporary:
        for key in list(os.environ):
            if key.startswith('YGG_'):
                del os.environ[key]
        os.environ.update(YGG_HOME=temporary, YGG_USER_ID='Demo', YGG_NAMESPACE='demo-workspace')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from yggdrasil import __version__
        from yggdrasil.ygg_memory_server import MemoryStore
        from yggdrasil.ygg_workspace import WorkspaceServer, WorkspaceHandler
        from yggdrasil.ygg_workspace_data import workspace_query
        from yggdrasil.ygg_workspace_management import Management

        home = Path(temporary)
        store = MemoryStore(str(home / 'demo.sqlite'))
        projects = {
            'Atlas Commerce': [
                ('decision', 'Use idempotency keys for checkout requests. A retry must return the original order instead of creating a second charge.', 'Architecture review'),
                ('lesson', 'Validate webhook signatures before parsing the event payload. Keep the original request bytes available for verification.', 'Engineering handbook'),
                ('project_status', 'Checkout redesign is ready for review. Inventory reservations and payment retries are covered; accessibility review is next.', 'Release checklist'),
                ('decision', 'Keep product availability in a dedicated read model. Update it from inventory events rather than querying the warehouse on each page load.', 'Architecture review'),
                ('lesson', 'A timed-out payment is not a failed payment. Reconcile with the provider before allowing a second attempt.', 'Incident review'),
                ('decision', 'Use cursor pagination for the order history. Offset pagination skips entries when new orders arrive between requests.', 'API design notes'),
                ('lesson', 'Cache product images independently of product prices so catalog updates do not invalidate every asset.', 'Performance notes'),
                ('project_status', 'The staging catalog contains synthetic products only. The next milestone is a monitored checkout rollout.', 'Release checklist'),
            ],
            'Orbit Notes': [
                ('decision', 'Store edits locally first and synchronize in the background. A disconnected session should remain fully usable.', 'Product specification'),
                ('lesson', 'Preserve the selection range when the editor receives a remote update.', 'Editor retrospective'),
                ('project_status', 'Offline drafts and conflict recovery are ready. Shared notebooks are in design review.', 'Weekly summary'),
                ('decision', 'Use a deterministic merge strategy for note titles and preserve both versions of conflicting body edits.', 'Architecture review'),
                ('lesson', 'Keep search indexing outside the typing path to avoid dropped keystrokes on large notes.', 'Performance notes'),
            ],
            'Beacon Analytics': [
                ('decision', 'Aggregate event counts by UTC hour and convert to the viewer timezone only at display time.', 'Data contract'),
                ('lesson', 'Late events require a rolling recomputation window. Daily dashboards must not freeze before that window closes.', 'Pipeline retrospective'),
                ('project_status', 'The usage dashboard supports saved filters and CSV exports. Cohort analysis is planned next.', 'Weekly summary'),
                ('decision', 'Treat missing metrics as unknown, not zero, so charts do not imply a sudden drop in usage.', 'Dashboard specification'),
            ],
            'Harbor API': [
                ('decision', 'Publish a versioned OpenAPI contract and check compatibility before merging endpoint changes.', 'API design notes'),
                ('lesson', 'Return a request identifier with every error to connect client reports to server logs.', 'Operations handbook'),
                ('project_status', 'Rate limiting and API key rotation are complete. The SDK examples are being reviewed.', 'Release checklist'),
                ('decision', 'Use exponential backoff with jitter for retryable upstream errors.', 'Reliability notes'),
            ],
            'Cedar Design System': [
                ('decision', 'Express component colors through semantic tokens so every control supports light and dark themes.', 'Design principles'),
                ('lesson', 'Keyboard focus should remain visible inside scroll containers and modal dialogs.', 'Accessibility review'),
                ('project_status', 'Forms, menus and notifications are documented. Data-table examples are the next milestone.', 'Component roadmap'),
                ('decision', 'Use one spacing scale across components and reserve animation for feedback on user actions.', 'Design principles'),
            ],
            'Nimbus Mobile': [
                ('decision', 'Queue network writes locally and show their pending state until the server acknowledges them.', 'Mobile architecture'),
                ('lesson', 'Restore navigation state after process termination instead of returning every user to the home screen.', 'QA retrospective'),
                ('project_status', 'The preview build includes offline lists, saved searches and accessible settings.', 'Release checklist'),
                ('decision', 'Keep background synchronization within the platform time budget and resume from the last checkpoint.', 'Mobile architecture'),
            ],
        }
        for project, records in projects.items():
            for index, (kind, content, source) in enumerate(records):
                store.add(content=content, user_id='Demo', namespace='demo-workspace', scope='project',
                          metadata={'project':project,'type':kind,'source':source})
        # Fixed synthetic dates keep docs reproducible; no host paths or accounts.
        with store._lock:
            store._conn.execute('UPDATE memories SET created_at=?', (1794823200,))
            store._conn.commit()
        query = lambda body: workspace_query(store, {**body,'user_id':'Demo','namespace':'demo-workspace'})
        jobs = [
            {'id':'demo-seed','command':'seed','args':['--dry-run'],'status':'completed',
             'output':'$ ygg seed --dry-run\n\nScanning demo conversation sources…\n  Atlas Commerce       8 conversations ready\n  Orbit Notes          5 conversations ready\n  Beacon Analytics     4 conversations ready\n\nPreview complete: 17 conversations found.\nNo files were imported or changed.\n',
             'exit_code':0,'created_at':1794823000,'finished_at':1794823010,'interactive':True,'truncated':False},
            {'id':'demo-doctor','command':'doctor','args':[],'status':'completed',
             'output':'Demo diagnostic output\nMemory database: ready\nLocal API: reachable\nConfiguration: valid\n',
             'exit_code':0,'created_at':1794822000,'finished_at':1794822002,'interactive':False,'truncated':False},
            {'id':'demo-sync','command':'sync','args':[],'status':'completed',
             'output':'Demo sync output\nAll demo records are up to date.\n',
             'exit_code':0,'created_at':1794810000,'finished_at':1794810004,'interactive':False,'truncated':False},
        ]
        class DemoHandler(WorkspaceHandler):
            def _api(self, path):
                if path == '/api/jobs' and self.command == 'GET':
                    return self._json(200, {'jobs':jobs})
                if path == '/api/release' and self.command == 'GET':
                    return self._json(200, {'current':__version__,'running':__version__,'latest':__version__,
                        'available':False,'checking':False,'check_error':False,'stars':22,
                        'repository':'https://github.com/VonderVuflya/Yggdrasil',
                        'releases':'https://github.com/VonderVuflya/Yggdrasil/releases',
                        'restart_required':False,'update':None})
                allowed = {'GET': {'/api/status','/api/projects','/api/commands','/api/config'},
                           'POST': {'/api/memories','/api/memory','/api/sources'}}
                if path not in allowed.get(self.command, set()):
                    return self._json(403, {'error':'Read-only fictional demo. Commands are disabled.'})
                return super()._api(path)
        server = WorkspaceServer(('127.0.0.1',args.port),home=home,query=query,
            control=secrets.token_urlsafe(48),user_id='Demo',namespace='demo-workspace')
        server.RequestHandlerClass = DemoHandler
        server._management = Management(home)
        url = f'http://127.0.0.1:{server.server_port}/#ticket={server.issue_ticket()}'
        print(json.dumps({'url':url,'port':server.server_port,'fictional':True}),flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            store._conn.close()


if __name__ == '__main__':
    main()
