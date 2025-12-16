ImportError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/mount/src/kv-kortrijk-platform/Home.py", line 128, in <module>
    pg.run()
    ~~~~~~^^
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/navigation/page.py", line 310, in run
    exec(code, module.__dict__)  # noqa: S102
    ~~~~^^^^^^^^^^^^^^^^^^^^^^^
File "/mount/src/kv-kortrijk-platform/views/1_⚽_Spelers.py", line 5, in <module>
    from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS
