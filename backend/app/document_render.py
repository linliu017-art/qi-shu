"""Render generated Word documents locally for visual review."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


class DocumentRenderError(Exception):
    pass


def render_word_pdf(content: bytes) -> bytes:
    project = Path(__file__).resolve().parents[2]
    configured = os.environ.get('QISHU_SOFFICE_PATH')
    local = project / '.tools/LibreOffice.app/Contents/MacOS/soffice'
    executable = configured or (str(local) if local.is_file() else shutil.which('soffice'))
    if not executable:
        raise DocumentRenderError('未配置本机文档渲染器，暂时无法预览分页。')
    if len(content) > 20 * 1024 * 1024:
        raise DocumentRenderError('文档过大，暂时无法生成分页预览。')
    with tempfile.TemporaryDirectory(prefix='qishu-render-') as temp:
        root = Path(temp)
        source = root / 'document.docx'
        source.write_bytes(content)
        profile = (root / 'profile').as_uri()
        try:
            result = subprocess.run([executable, '--headless', f'-env:UserInstallation={profile}',
                                     '--convert-to', 'pdf:writer_pdf_Export', '--outdir', str(root), str(source)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=60, check=False,
                                    env={'PATH': os.defpath, 'HOME': str(root), 'TMPDIR': str(root), 'LANG': 'en_US.UTF-8'})
        except (OSError, subprocess.TimeoutExpired):
            raise DocumentRenderError('分页预览未能生成，请稍后重试。') from None
        output = root / 'document.pdf'
        if result.returncode != 0 or not output.is_file() or output.stat().st_size > 50 * 1024 * 1024:
            raise DocumentRenderError('分页预览未能生成，请稍后重试。')
        data = output.read_bytes()
        if not data.startswith(b'%PDF-'):
            raise DocumentRenderError('分页预览文件无效，请稍后重试。')
        return data
