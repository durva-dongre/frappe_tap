import frappe
from frappe import _
from frappe.utils import now
import json
from typing import Dict, List, Any, Tuple

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
        course_project = create_or_update_course_project(activity_data)
        
        if activity_data.get('video_urls'):
            create_or_update_videos(activity_data)
        
        if activity_data.get('scripts'):
            create_or_update_note_content(activity_data)
        
        if activity_data.get('quizzes'):
            create_quizzes(activity_data)
        
        link_content_to_unit(learning_unit, course_project, activity_data)
        
        return {
            'success': True,
            'message': 'Activity processed successfully',
            'activity_data': {
                'unit_no': unit_no,
                'activity_name': activity_name,
                'learning_unit_id': learning_unit.name,
                'course_project_id': course_project.name
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'message': str(e),
            'activity_data': None
        }

def create_or_update_learning_unit(activity_data: Dict) -> Any:
    unit_no = activity_data.get('unit_no')
    unit_name = f"{unit_no}-{activity_data.get('activity_name', '')}"
    
    existing_unit = frappe.db.exists('LearningUnit', {'unit_name': unit_name})
    
    if existing_unit:
        learning_unit = frappe.get_doc('LearningUnit', existing_unit)
    else:
        learning_unit = frappe.new_doc('LearningUnit')
        learning_unit.unit_name = unit_name
        learning_unit.unit_type = 'Lesson'
        learning_unit.difficulty_tier = activity_data.get('difficulty_tier', 'Intermediate')
        
        try:
            order_num = int(''.join(filter(str.isdigit, unit_no.split('-')[0]))) if '-' in unit_no else 1
        except:
            order_num = 1
        
        learning_unit.order = order_num
    
    learning_unit.description = activity_data.get('description', '')
    learning_unit.save(ignore_permissions=True)
    
    return learning_unit

def create_or_update_course_project(activity_data: Dict) -> Any:
    project_name = activity_data.get('activity_name')
    
    existing_project = frappe.db.exists('CourseProject', {'project_name': project_name})
    
    if existing_project:
        course_project = frappe.get_doc('CourseProject', existing_project)
    else:
        course_project = frappe.new_doc('CourseProject')
        course_project.project_name = project_name
    
    course_project.description = activity_data.get('description', '')
    course_project.save(ignore_permissions=True)
    
    return course_project

def create_or_update_videos(activity_data: Dict) -> None:
    video_urls = activity_data.get('video_urls', {})
    
    for language, url_data in video_urls.items():
        if not url_data or not url_data.get('youtube_url'):
            continue
        
        video_name = f"{activity_data.get('activity_name')}-{language}"
        
        existing_video = frappe.db.exists('VideoClass', {'video_name': video_name})
        
        if existing_video:
            video_class = frappe.get_doc('VideoClass', existing_video)
        else:
            video_class = frappe.new_doc('VideoClass')
            video_class.video_name = video_name
        
        video_class.description = activity_data.get('description', '')
        video_class.video_youtube_url = url_data.get('youtube_url', '')
        
        if url_data.get('plio_url'):
            video_class.video_plio_url = url_data.get('plio_url')
        
        video_class.save(ignore_permissions=True)

def create_or_update_note_content(activity_data: Dict) -> None:
    scripts = activity_data.get('scripts', {})
    
    for language, script_text in scripts.items():
        if not script_text:
            continue
        
        note_name = f"{activity_data.get('activity_name')}-Script-{language}"
        
        existing_note = frappe.db.exists('NoteContent', {'note_name': note_name})
        
        if existing_note:
            note_content = frappe.get_doc('NoteContent', existing_note)
        else:
            note_content = frappe.new_doc('NoteContent')
            note_content.note_name = note_name
            note_content.note_type = 'Reading_Material'
        
        note_content.content = script_text
        note_content.save(ignore_permissions=True)

def create_quizzes(activity_data: Dict) -> None:
    quizzes = activity_data.get('quizzes', {})
    
    language_mapping = {
        'english': 'English',
        'hindi': 'Hindi',
        'marathi': 'Marathi',
        'punjabi': 'Punjabi',
        'hinglish': 'Hinglish'
    }
    
    for language, quiz_data in quizzes.items():
        if not quiz_data or 'questions' not in quiz_data:
            continue
        
        quiz_name = f"{activity_data.get('activity_name')}-{language}"
        
        existing_quiz = frappe.db.exists('Quiz', {'quiz_name': quiz_name})
        
        if existing_quiz:
            quiz = frappe.get_doc('Quiz', existing_quiz)
            quiz.set('questions', [])
        else:
            quiz = frappe.new_doc('Quiz')
            quiz.quiz_name = quiz_name
            
            proper_language = language_mapping.get(language.lower(), language.capitalize())
            
            if frappe.db.exists('Language', proper_language):
                quiz.language = proper_language
        
        quiz.description = activity_data.get('description', '')
        quiz.total_questions = len(quiz_data.get('questions', []))
        
        for q_idx, question_data in enumerate(quiz_data.get('questions', []), 1):
            if not question_data or 'text' not in question_data:
                continue
            
            question_name = f"{quiz_name}-Q{q_idx}"
            
            existing_question = frappe.db.exists('QuizQuestion', {'question_name': question_name})
            
            if existing_question:
                question_doc = frappe.get_doc('QuizQuestion', existing_question)
            else:
                question_doc = frappe.new_doc('QuizQuestion')
                question_doc.question_name = question_name
            
            question_doc.question = question_data.get('text', '')
            question_doc.question_type = 'Multiple Choice'
            question_doc.correct_option = question_data.get('correct_option', 1)
            
            question_doc.set('options', [])
            
            for opt_idx, option_text in enumerate(question_data.get('options', []), 1):
                if option_text:
                    question_doc.append('options', {
                        'option_text': option_text,
                        'option_number': opt_idx
                    })
            
            question_doc.save(ignore_permissions=True)
            
            quiz.append('questions', {
                'question_number': q_idx,
                'question': question_doc.name
            })
        
        quiz.save(ignore_permissions=True)

def link_content_to_unit(learning_unit: Any, course_project: Any, activity_data: Dict) -> None:
    learning_unit.set('content_items', [])
    
    learning_unit.append('content_items', {
        'content_type': 'CourseProject',
        'content': course_project.name,
        'is_optional': 0
    })
    
    if activity_data.get('video_urls'):
        for language in activity_data['video_urls'].keys():
            video_name = f"{activity_data.get('activity_name')}-{language}"
            if frappe.db.exists('VideoClass', video_name):
                learning_unit.append('content_items', {
                    'content_type': 'VideoClass',
                    'content': video_name,
                    'is_optional': 0
                })
    
    if activity_data.get('scripts'):
        for language in activity_data['scripts'].keys():
            note_name = f"{activity_data.get('activity_name')}-Script-{language}"
            if frappe.db.exists('NoteContent', note_name):
                learning_unit.append('content_items', {
                    'content_type': 'NoteContent',
                    'content': note_name,
                    'is_optional': 0
                })
    
    if activity_data.get('quizzes'):
        for language in activity_data['quizzes'].keys():
            quiz_name = f"{activity_data.get('activity_name')}-{language}"
            if frappe.db.exists('Quiz', quiz_name):
                learning_unit.append('content_items', {
                    'content_type': 'Quiz',
                    'content': quiz_name,
                    'is_optional': 0
                })
    
    learning_unit.save(ignore_permissions=True)