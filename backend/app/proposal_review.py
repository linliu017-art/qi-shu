"""确定性核验方案引用的已保存资料；不调用模型。"""
import hashlib
import json
from pathlib import Path
from sqlalchemy import func, select
from .analysis import align_quote
from . import database
from .models import Baseline, BaselineFacts, BaselineQuestions, ExtractedFact, FactReview, Material, MaterialOriginal, MaterialVersion, ManualRequirement, OpenQuestion, ProposalDraft, ProposalInputSource, QuestionDecision, Requirement

class SourceCheckError(Exception):
    pass

def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def questions_for(db, draft: ProposalDraft):
    row = db.get(BaselineQuestions, draft.baseline_id)
    if not row:
        raise SourceCheckError('这份旧需求清单缺少待确认问题记录，请重新生成清单和方案。')
    questions = json.loads(row.snapshot)
    if not isinstance(questions, list) or any(not q.get('id') or not q.get('text') for q in questions):
        raise SourceCheckError('需求清单中的待确认问题无法核对。')
    if len({q['id'] for q in questions}) != len(questions):
        raise SourceCheckError('需求清单中的待确认问题存在重复，无法审核。')
    return questions

def source_snapshot(db, draft: ProposalDraft, template_path: Path, example_path: Path):
    baseline = db.scalar(select(Baseline).where(Baseline.id == draft.baseline_id, Baseline.project_id == draft.project_id))
    if not baseline:
        raise SourceCheckError('找不到方案使用的需求清单。')
    try:
        requirements = json.loads(baseline.snapshot)
        questions = questions_for(db, draft)
        inputs = json.loads(draft.input_snapshot)
        if not isinstance(requirements, list) or not requirements:
            raise SourceCheckError('需求清单没有可核对的需求。')
        for entry in requirements:
            if not entry.get('id') or not isinstance(entry.get('version'), int):
                raise SourceCheckError('这份旧需求清单缺少版本信息，请重新生成清单和方案。')
            if entry.get('origin') == 'manual':
                current = db.scalar(select(ManualRequirement).where(ManualRequirement.id == entry['id'], ManualRequirement.project_id == draft.project_id))
                if not current or current.status != 'confirmed' or current.version != entry['version'] or current.text != entry.get('text') or (current.material_id or '') != entry.get('material_id', '') or (current.quote or '') != entry.get('quote', ''):
                    raise SourceCheckError('方案关联的人工需求已变化，请重新生成清单和方案后审核。')
            else:
                current = db.scalar(select(Requirement).where(Requirement.id == entry['id'], Requirement.project_id == draft.project_id))
                if not current or current.status != 'confirmed' or current.version != entry['version'] or current.text != entry.get('text') or current.quote != entry.get('quote') or current.material_id != entry.get('material_id'):
                    raise SourceCheckError('方案关联的需求已变化，请重新生成清单和方案后审核。')
        for entry in questions:
            current = db.scalar(select(OpenQuestion).where(OpenQuestion.id == entry['id'], OpenQuestion.project_id == draft.project_id))
            latest = db.scalar(select(QuestionDecision).where(QuestionDecision.question_id == entry['id']).order_by(QuestionDecision.created_at.desc())) if current else None
            current_answer = latest.answer if latest else ''
            if not current or current.text != entry.get('text') or current.status != entry.get('status') or current_answer != entry.get('answer', ''):
                raise SourceCheckError('方案关联的问题已变化，请重新生成清单和方案后审核。')
        fact_record = db.get(BaselineFacts, baseline.id)
        facts = json.loads(fact_record.snapshot) if fact_record else []
        if not isinstance(facts, list):
            raise SourceCheckError('需求清单中的资料事实无法核对。')
        for entry in facts:
            if not isinstance(entry, dict) or not entry.get('id') or not isinstance(entry.get('review_version'), int):
                raise SourceCheckError('需求清单中的资料事实无法核对。')
            current = db.scalar(select(ExtractedFact).where(ExtractedFact.id == entry['id'], ExtractedFact.project_id == draft.project_id))
            review = db.get(FactReview, entry['id']) if current else None
            if not current or not review or review.status != 'reviewed' or review.version != entry['review_version'] or current.text != entry.get('text') or current.material_id != entry.get('material_id') or current.quote != entry.get('quote'):
                raise SourceCheckError('方案关联的资料事实核对状态已变化，请重新生成清单和方案后审核。')
        input_sources = list(db.scalars(select(ProposalInputSource).where(ProposalInputSource.project_id == draft.project_id, ProposalInputSource.draft_id == draft.id)))
        template_sources = [source for source in input_sources if source.kind == 'template']
        if draft.template_id == 'demo-v1':
            current_template = template_path.read_text(encoding='utf-8')
            if current_template != draft.template_snapshot:
                raise SourceCheckError('方案所用模板已变化，请重新生成方案后审核。')
        else:
            if len(template_sources) != 1 or template_sources[0].material_id != draft.template_id:
                raise SourceCheckError('方案模板依据无法核对。')
            current_template = draft.template_snapshot
        extra_sources = {}
        for source in input_sources:
            material=db.scalar(select(Material).where(Material.project_id==draft.project_id,Material.id==source.material_id))
            version=db.get(MaterialVersion,source.material_id) if material else None
            original=db.get(MaterialOriginal,source.material_id) if material else None
            if not material or not version or not original or version.state != 'active' or version.version != source.version or version.state_version != source.state_version or original.sha256 != source.file_hash or digest_text(material.text) != source.text_hash:
                raise SourceCheckError('方案使用的模板或案例已变化或撤回，请重新核对。')
            if source.kind == 'template' and material.text != draft.template_snapshot:
                raise SourceCheckError('方案所用模板已变化，请重新核对。')
            path=database.DATA_DIR / 'materials' / original.filename_on_disk
            if original.filename_on_disk != material.id or not path.is_file():
                raise SourceCheckError('方案模板或案例原件不可用。')
            hasher=hashlib.sha256()
            with path.open('rb') as file:
                for chunk in iter(lambda:file.read(1024*1024),b''):hasher.update(chunk)
            if hasher.hexdigest() != source.file_hash:
                raise SourceCheckError('方案模板或案例原件已变化。')
            extra_sources[source.kind + ':' + source.material_id]={'version':source.version,'state_version':source.state_version,'file':source.file_hash,'text':source.text_hash}
            latest = db.scalar(select(func.max(MaterialVersion.version)).where(MaterialVersion.project_id==draft.project_id,MaterialVersion.group_id==version.group_id)) or version.version
            if latest > version.version:
                extra_sources[source.kind + ':' + source.material_id]['latest_version'] = latest

        example_keys = [key for key in inputs if key.startswith('虚构参考案例')]
        if any(inputs[key] != example_path.read_text(encoding='utf-8') for key in example_keys):
            raise SourceCheckError('方案所用参考案例已变化，请重新生成方案后审核。')
        references = []
        for entry in requirements + questions + facts:
            for source in [entry] + (entry.get('related_sources') or []):
                if source.get('material_id') or source.get('quote'):
                    references.append((source.get('material_id'), source.get('quote')))
        if not references and not all(entry.get('origin') == 'manual' for entry in requirements):
            raise SourceCheckError('方案所用清单没有可核对的资料出处。')
        found = {}
        for material_id, quote in references:
            if not material_id or not quote:
                raise SourceCheckError('需求清单中有无法核对的资料出处。')
            material = db.scalar(select(Material).where(Material.id == material_id, Material.project_id == draft.project_id, Material.owner_id == 'local-user'))
            record = db.get(MaterialOriginal, material_id) if material else None
            version = db.get(MaterialVersion, material_id) if material else None
            if version and version.state != 'active':
                raise SourceCheckError('方案引用的资料已撤回，请重新核对。')
            if not material or not record or record.filename_on_disk != material_id or not align_quote(quote, material.text):
                raise SourceCheckError('需求清单中有无法核对的资料出处。')
            if material_id not in found:
                path = database.DATA_DIR / 'materials' / record.filename_on_disk
                if not path.is_file():
                    raise SourceCheckError('方案引用的原文件不可用。')
                file_hash = hashlib.sha256()
                with path.open('rb') as file:
                    for chunk in iter(lambda: file.read(1024 * 1024), b''):
                        file_hash.update(chunk)
                if file_hash.hexdigest() != record.sha256:
                    raise SourceCheckError('方案引用的原文件发生变化，请先核对。')
                found[material_id] = {'file': record.sha256, 'text': digest_text(material.text), 'name': material.filename}
                if version and version.state_version:
                    found[material_id]['state_version'] = version.state_version
                if version:
                    latest = db.scalar(select(func.max(MaterialVersion.version)).where(MaterialVersion.project_id==draft.project_id,MaterialVersion.group_id==version.group_id)) or version.version
                    if latest > version.version:
                        found[material_id]['latest_version'] = latest
        result = {'baseline': digest_text(baseline.snapshot), 'questions': digest_text(json.dumps(questions, ensure_ascii=False, sort_keys=True)),
                  'template': digest_text(current_template), 'inputs': digest_text(draft.input_snapshot),
                  'content': digest_text(draft.content), 'materials': found}
        if extra_sources:
            result['additional_sources'] = extra_sources
        if fact_record:
            result['facts'] = digest_text(fact_record.snapshot)
        return result
    except SourceCheckError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise SourceCheckError('方案依据暂时无法核对，请检查资料后重试。') from None
