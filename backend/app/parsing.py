import io
import zipfile
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
import pdfplumber

class ParseError(Exception):
    pass

def parse_content(name: str, content: bytes) -> tuple[str, str]:
    lower = name.lower()
    if lower.endswith(('.txt', '.md')):
        if b'\x00' in content:
            raise ParseError('文件不是可读取的文字资料。')
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ParseError('请使用 UTF-8 编码的文字文件。') from None
        note = ''
    elif lower.endswith('.pdf'):
        if not content.startswith(b'%PDF-'):
            raise ParseError('文件内容与 PDF 格式不符。')
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ParseError('文件已加密，请先解除加密。')
            sections = []
            unread_pages = []
            table_errors = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    try:
                        body = page.extract_text() or ''
                    except Exception:
                        unread_pages.append(i)
                        continue
                    if not body.strip():
                        unread_pages.append(i)
                        continue
                    sections.append(f'[第{i}页]\n{body}')
                    try:
                        tables = page.extract_tables()
                    except Exception:
                        table_errors.append(i)
                        continue
                    for table_index, table in enumerate(tables, 1):
                        if not table:
                            continue
                        sections.append(f'[第{i}页 表格{table_index}]')
                        for row in table:
                            sections.append(' | '.join((cell or '').replace('\n', ' ') for cell in row))
            text = '\n'.join(sections)
            note = '图片和复杂表格可能未完整读取，请核对原件。'
            if unread_pages:
                note += ' 未读取文字的页面：' + '、'.join(map(str, unread_pages)) + '。'
            if table_errors:
                note += ' 表格读取失败的页面：' + '、'.join(map(str, table_errors)) + '。'
        except ParseError:
            raise
        except Exception:
            raise ParseError('无法读取 PDF，请检查文件是否损坏。') from None
    elif lower.endswith('.docx'):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(i.file_size for i in entries) > 200 * 1024 * 1024:
                    raise ParseError('文档解压后过大，无法安全读取。')
                if '[Content_Types].xml' not in archive.namelist() or 'word/document.xml' not in archive.namelist():
                    raise ParseError('文件内容与 DOCX 格式不符。')
            doc = Document(io.BytesIO(content))
            parts = []
            for block in doc.iter_inner_content():
                if isinstance(block, Paragraph) and block.text.strip():
                    parts.append(block.text)
                elif isinstance(block, Table):
                    for row in block.rows:
                        parts.append(' | '.join(cell.text for cell in row.cells))
            text = '\n'.join(parts)
            note = '图片、复杂合并或嵌套表格可能未完整读取，请核对原件。'
        except ParseError:
            raise
        except Exception:
            raise ParseError('无法读取 DOCX，请检查文件是否损坏。') from None
    else:
        raise ParseError('不支持此格式，请使用 TXT、Markdown、文字型 PDF 或 DOCX。')
    if not text.strip():
        raise ParseError('没有读取到文字；扫描件和图片暂不支持识别。')
    return text, note
