import frappe
from frappe import _
from frappe.utils import now, cstr
import json
import re
from typing import Dict, List, Any, Optional

@frappe.whitelist(allow_guest=False, methods=['POST'])
def sync_curriculum_data():
    try:
        data = frappe.request.get_json()
        
        if not data:
            return {
                'status': 'error',
                'message': 'No data provided',
                'errors': []
            }
        
        validation_result = validate_payload(data)
        if not validation_result['valid']:
            return {
                'status': 'error',
                'message': 'Validation failed',
                'errors': validation_result['errors']
            }
        
        processed_activities = []
        errors = []
        
        for idx, activity_data in enumerate(data.get('activities', [])):
            try:
                result = process_activity(activity_data, idx)
                if result['success']:
                    processed_activities.append(result['activity_data'])
                else:
                    errors.append({
                        'row': idx + 1,
                        'error': result['message'],
                        'activity': activity_data.get('activity_name', 'Unknown')
                    })
            except Exception as e:
                frappe.log_error(f"Error processing activity {idx + 1}: {str(e)}", "Curriculum Sync Error")
                errors.append({
                    'row': idx + 1,
                    'error': str(e),
                    'activity': activity_data.get('activity_name', 'Unknown')
                })
        
        frappe.db.commit()
        
        return {
            'status': 'success' if not errors else 'partial',
            'message': f'Processed {len(processed_activities)} activities successfully',
            'processed_count': len(processed_activities),
            'error_count': len(errors),
            'errors': errors,
            'activities': processed_activities
        }
    
    except Exception as e:
        frappe.log_error(f"Server error in curriculum sync: {str(e)}", "Curriculum Sync Error")
        frappe.db.rollback()
        return {
            'status': 'error',
            'message': f'Server error: {str(e)}',
            'errors': []
        }


def validate_payload(data: Dict) -> Dict[str, Any]:
    errors = []
    
    if not isinstance(data, dict):
        errors.append('Payload must be a dictionary')
        return {'valid': False, 'errors': errors}
    
    if 'activities' not in data:
        errors.append('Missing "activities" key in payload')
        return {'valid': False, 'errors': errors}
    
    if not isinstance(data['activities'], list):
        errors.append('"activities" must be a list')
        return {'valid': False, 'errors': errors}
    
    if len(data['activities']) == 0:
        errors.append('No activities provided')
        return {'valid': False, 'errors': errors}
    
    return {'valid': True, 'errors': []}

def process_activity(activity_data: Dict, row_idx: int) -> Dict[str, Any]:
    try:
        unit_no = activity_data.get('unit_no')
        activity_name = activity_data.get('activity_name')
        
        if not unit_no or not activity_name:
            return {
                'success': False,
                'message': 'Missing unit_no or activity_name',
                'activity_data': None
            }
        
        learning_unit = create_or_update_learning_unit(activity_data)
        
        video_classes = {}
        if activity_data.get('video_urls'):
            video_classes = create_or_update_videos(activity_data)
        
        note_contents = {}
        if activity_data.get('scripts'):
            note_contents = create_or_update_note_content(activity_data)
        
        quizzes = {}
        if activity_data.get('quizzes'):
            quizzes = create_or_update_quizzes(activity_data, 'quiz')
        
        plio_quizzes = {}
        if activity_data.get('plio_quizzes'):
            plio_quizzes = create_or_update_quizzes(activity_data, 'plio')
        
        link_content_to_unit(learning_unit, video_classes, note_contents, quizzes, plio_quizzes)
        
        return {
            'success': True,
            'message': 'Activity processed successfully',
            'activity_data': {
                'unit_no': unit_no,
                'activity_name': activity_name,
                'learning_unit_id': learning_unit.name,
                'video_classes': list(video_classes.keys()),
                'note_contents': list(note_contents.keys()),
                'quizzes': list(quizzes.keys()),
                'plio_quizzes': list(plio_quizzes.keys())
            }
        }
    
    except Exception as e:
        frappe.log_error(f"Error in process_activity: {str(e)}", "Process Activity Error")
        return {
            'success': False,
            'message': str(e),
            'activity_data': None
        }

def create_or_update_learning_unit(activity_data: Dict) -> Any:
    unit_no = activity_data.get('unit_no', '')
    activity_name = activity_data.get('activity_name', '')
    
    unit_id = generate_id(f"{unit_no}-{activity_name}")
    
    existing_unit = frappe.db.exists('LearningUnit', {'unit_name': unit_id})
    
    if existing_unit:
        learning_unit = frappe.get_doc('LearningUnit', existing_unit)
    else:
        learning_unit = frappe.new_doc('LearningUnit')
        learning_unit.unit_name = unit_id
        learning_unit.unit_type = 'Lesson'
        learning_unit.difficulty_tier = 'Intermediate'
        
        try:
            order_num = extract_order_number(unit_no)
        except:
            order_num = 1
        
        learning_unit.order = order_num
    
    learning_unit.description = clean_text(activity_data.get('description', ''))
    
    if activity_data.get('objectives'):
        learning_unit.description += f"\n\nObjectives: {clean_text(activity_data.get('objectives', ''))}"
    
    if activity_data.get('outcomes'):
        learning_unit.description += f"\n\nOutcomes: {clean_text(activity_data.get('outcomes', ''))}"
    
    learning_unit.save(ignore_permissions=True)
    
    return learning_unit

def create_or_update_videos(activity_data: Dict) -> Dict[str, str]:
    video_urls = activity_data.get('video_urls', {})
    activity_name = activity_data.get('activity_name', '')
    
    created_videos = {}
    
    for language, url_data in video_urls.items():
        if not url_data or not isinstance(url_data, dict):
            continue
        
        youtube_url = url_data.get('youtube_url', '')
        plio_url = url_data.get('plio_url', '')
        drive_url = url_data.get('drive_url', '')
        
        if not youtube_url and not plio_url and not drive_url:
            continue
        
        video_id = generate_id(f"{activity_name}-video-{language}")
        
        existing_video = frappe.db.exists('VideoClass', {'video_name': video_id})
        
        if existing_video:
            video_class = frappe.get_doc('VideoClass', existing_video)
        else:
            video_class = frappe.new_doc('VideoClass')
            video_class.video_name = video_id
            video_class.difficulty_tier = 'Intermediate'
        
        video_class.description = f"{activity_name} - {language}"
        
        if youtube_url:
            video_class.video_youtube_url = youtube_url
        
        if plio_url:
            video_class.video_plio_url = plio_url
        
        video_class.save(ignore_permissions=True)
        created_videos[language] = video_class.name
    
    return created_videos

def create_or_update_note_content(activity_data: Dict) -> Dict[str, str]:
    scripts = activity_data.get('scripts', {})
    activity_name = activity_data.get('activity_name', '')
    
    created_notes = {}
    
    for language, script_text in scripts.items():
        if not script_text:
            continue
        
        note_id = generate_id(f"{activity_name}-script-{language}")
        
        existing_note = frappe.db.exists('NoteContent', {'note_name': note_id})
        
        if existing_note:
            note_content = frappe.get_doc('NoteContent', existing_note)
        else:
            note_content = frappe.new_doc('NoteContent')
            note_content.note_name = note_id
            note_content.note_type = 'Reading_Material'
            note_content.difficulty_tier = 'Intermediate'
        
        note_content.content = clean_text(script_text)
        note_content.save(ignore_permissions=True)
        created_notes[language] = note_content.name
    
    return created_notes

def create_or_update_quizzes(activity_data: Dict, quiz_type: str = 'quiz') -> Dict[str, str]:
    quiz_key = 'plio_quizzes' if quiz_type == 'plio' else 'quizzes'
    quizzes_data = activity_data.get(quiz_key, {})
    activity_name = activity_data.get('activity_name', '')
    
    created_quizzes = {}
    
    language_mapping = {
        'english': 'English',
        'hindi': 'Hindi',
        'marathi': 'Marathi',
        'punjabi': 'Punjabi',
        'hinglish': 'Hinglish'
    }
    
    for language, quiz_data in quizzes_data.items():
        if not quiz_data or 'questions' not in quiz_data:
            continue
        
        if not quiz_data['questions']:
            continue
        
        quiz_id = generate_id(f"{activity_name}-{quiz_type}-{language}")
        
        existing_quiz = frappe.db.exists('Quiz', {'quiz_name': quiz_id})
        
        if existing_quiz:
            quiz = frappe.get_doc('Quiz', existing_quiz)
            quiz.set('questions', [])
        else:
            quiz = frappe.new_doc('Quiz')
            quiz.quiz_name = quiz_id
            quiz.difficulty_tier = 'Intermediate'
            
            proper_language = language_mapping.get(language.lower(), language.capitalize())
            
            if frappe.db.exists('TAP Language', proper_language):
                quiz.language = proper_language
        
        quiz.description = f"{activity_name} - {language} {quiz_type.capitalize()}"
        quiz.total_questions = len(quiz_data.get('questions', []))
        
        for q_idx, question_data in enumerate(quiz_data.get('questions', []), 1):
            if not question_data or 'text' not in question_data:
                continue
            
            question_id = generate_id(f"{quiz_id}-q{q_idx}")
            
            existing_question = frappe.db.exists('QuizQuestion', {'question_name': question_id})
            
            if existing_question:
                question_doc = frappe.get_doc('QuizQuestion', existing_question)
                question_doc.set('options', [])
            else:
                question_doc = frappe.new_doc('QuizQuestion')
                question_doc.question_name = question_id
            
            question_doc.question = clean_text(question_data.get('text', ''))
            question_doc.question_type = 'Multiple Choice'
            question_doc.correct_option = int(question_data.get('correct_option', 1))
            
            for opt_idx, option_text in enumerate(question_data.get('options', []), 1):
                if option_text:
                    question_doc.append('options', {
                        'option_text': clean_text(option_text),
                        'option_number': opt_idx
                    })
            
            question_doc.save(ignore_permissions=True)
            
            quiz.append('questions', {
                'question_number': q_idx,
                'question': question_doc.name
            })
        
        quiz.save(ignore_permissions=True)
        created_quizzes[language] = quiz.name
    
    return created_quizzes

def link_content_to_unit(learning_unit: Any, video_classes: Dict, note_contents: Dict, 
                         quizzes: Dict, plio_quizzes: Dict) -> None:
    
    learning_unit.set('content_items', [])
    
    for language, video_name in video_classes.items():
        if frappe.db.exists('VideoClass', video_name):
            learning_unit.append('content_items', {
                'content_type': 'VideoClass',
                'content': video_name,
                'is_optional': 0
            })
    
    for language, note_name in note_contents.items():
        if frappe.db.exists('NoteContent', note_name):
            learning_unit.append('content_items', {
                'content_type': 'NoteContent',
                'content': note_name,
                'is_optional': 0
            })
    
    for language, quiz_name in quizzes.items():
        if frappe.db.exists('Quiz', quiz_name):
            learning_unit.append('content_items', {
                'content_type': 'Quiz',
                'content': quiz_name,
                'is_optional': 0
            })
    
    for language, plio_quiz_name in plio_quizzes.items():
        if frappe.db.exists('Quiz', plio_quiz_name):
            learning_unit.append('content_items', {
                'content_type': 'Quiz',
                'content': plio_quiz_name,
                'is_optional': 0
            })
    
    learning_unit.save(ignore_permissions=True)

def generate_id(text: str) -> str:
    if not text:
        return ''
    
    text = cstr(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    
    if len(text) > 140:
        text = text[:140]
    
    return text

def extract_order_number(unit_no: str) -> int:
    if not unit_no:
        return 1
    
    numbers = re.findall(r'\d+', cstr(unit_no))
    
    if numbers:
        return int(numbers[0])
    
    return 1

def clean_text(text: str) -> str:
    if not text:
        return ''
    
    text = cstr(text)
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    
    return text