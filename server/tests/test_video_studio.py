"""Video output is playable and creator exports require operator authorization."""
from io import BytesIO
import json
from pathlib import Path
import subprocess

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image

from server.api import create_app


def _photo():
    buffer = BytesIO()
    Image.new('RGB', (120, 180), '#347b9a').save(buffer, 'PNG')
    return buffer.getvalue()


def test_video_studio_requires_operator_and_renders_mp4(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'creator.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
    app = create_app(url, 'operator-token-longer-than-thirty-two-characters')
    payload = dict(headline='Uma ideia útil', message='Confira os detalhes antes de comprar',
                   call_to_action='Siga para novas dicas')
    files = {'photo': ('original.png', _photo(), 'image/png')}
    anonymous = TestClient(app)
    assert anonymous.post('/v1/creator-video', data=payload, files=files).status_code == 401
    with TestClient(app, headers={'Authorization': 'Bearer operator-token-longer-than-thirty-two-characters'}) as client:
        response = client.post('/v1/creator-video', data=payload, files=files)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'video/mp4'
        output = tmp_path / 'clip.mp4'
        output.write_bytes(response.content)
        info = subprocess.run(['ffprobe', '-v', 'error', '-of', 'json', '-show_streams', str(output)],
                              capture_output=True, text=True, check=True)
        stream = json.loads(info.stdout)['streams'][0]
        assert (stream['width'], stream['height']) == (540, 960)
        assert stream['codec_name'] == 'h264'
        too_large = client.post('/v1/creator-video', data=payload,
                                files={'photo': ('large.png', b'0' * 3_000_001, 'image/png')})
        assert too_large.status_code == 413
