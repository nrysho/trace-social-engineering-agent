"""Record a SYNTHETIC local-bench backup. No provider or real simulator calls.
Run after prepare_bench_fixture.py. Requires Playwright + installed Chrome/FFmpeg.
"""
import json,os,sys,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_quality_bench import BenchTests
from quality.craft import review_bundle
from viewer import serve

root=Path(__file__).resolve().parents[1]
out=root/'runs/quality/backup';out.mkdir(parents=True,exist_ok=True)
BenchTests.setUpClass()
try:
    for label,invalid,correct in [('accepted',True,True),('blocked',True,False)]:
        test=BenchTests();test.setUp()
        try:
            agent,bundle,_=test.run_agent(invalid=invalid,correct=correct)
            bundle.update(run_id='synthetic-bench-'+label,mode='bench-eval',synthetic=True,
                          agent_version='qa-smoke-deterministic',provenance='Local bench; deterministic fake persona engine')
            for node in bundle['nodes']:node['run_id']=bundle['run_id']
            (out/(label+'.json')).write_text(json.dumps(bundle,indent=2),encoding='utf-8')
        finally:test.doCleanups()
finally:BenchTests.tearDownClass()
accepted=json.loads((out/'accepted.json').read_text(encoding='utf-8'))
review_bundle(accepted,out/'craft',approved_domains=['events.example'])
loaders={label:(lambda name=label:json.loads((out/(name+'.json')).read_text(encoding='utf-8'))) for label in ('accepted','blocked')}
with patch.object(serve,'bundles',return_value=loaders):
    http=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':900},record_video_dir=str(out/'video'),record_video_size={'width':1440,'height':900})
            page=context.new_page()
            page.add_init_script("""document.addEventListener('DOMContentLoaded',()=>{
              const label=document.createElement('div');
              label.textContent='SYNTHETIC LOCAL BENCH - deterministic fake persona responses; no official simulator calls';
              label.style.cssText='position:fixed;right:20px;top:75px;max-width:460px;padding:12px;background:#664100;color:white;border:2px solid #e8b760;border-radius:8px;z-index:100000;font:600 15px/1.5 system-ui;pointer-events:none';
              document.body.append(label);
            })""")
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{http.server_port}/') else route.abort())
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{http.server_port}/')
            page.wait_for_function('run !== null && order.length > 0')
            page.evaluate("select(order.find(n=>n.level==='contact') || order[0])")
            page.screenshot(path=str(out/'replay-synthetic.png'),full_page=True)
            page.wait_for_timeout(1600)
            page.select_option('#runPick','blocked')
            page.wait_for_function("run.run_id==='synthetic-bench-blocked'")
            page.evaluate("select(order.find(n=>n.level==='attempt') || order[0])")
            page.wait_for_timeout(1600)
            page.screenshot(path=str(out/'blocked-synthetic.png'),full_page=True)
            video=page.video
            context.close()
            video.save_as(str(out/'person5-bench-backup.webm'))
            browser.close()
            if errors:raise RuntimeError('Viewer errors: '+str(errors))
    finally:http.shutdown();http.server_close();thread.join()
print('SYNTHETIC local-bench backup:',out/'person5-bench-backup.webm')
