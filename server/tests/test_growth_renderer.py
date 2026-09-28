import json
import subprocess
from server.growth_renderer import render_growth_plan

def test_growth_plan_renders_valid_vertical_mp4():
    plan = json.dumps({"hook":"Você sabia disso?","script":"Um teste original de conteúdo para crescimento legítimo.","caption":"Siga para mais."})
    output, digest, cleanup = render_growth_plan(plan)
    try:
        assert len(digest) == 64
        probe = subprocess.run(["ffprobe","-v","error","-of","json","-show_streams",str(output)],
                               capture_output=True,text=True,check=True)
        stream = json.loads(probe.stdout)["streams"][0]
        assert (stream["width"], stream["height"]) == (540, 960)
        assert stream["codec_name"] == "h264"
        assert output.stat().st_size > 0
    finally:
        cleanup()

def test_growth_plan_fails_closed_without_script():
    try:
        render_growth_plan(json.dumps({"hook":"x"}))
        assert False
    except ValueError:
        pass
