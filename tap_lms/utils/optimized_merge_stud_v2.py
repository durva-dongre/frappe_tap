"""
==============================================================================
STUDENT DUPLICATE MERGER - OPTIMIZED VERSION FOR LAPLMS
==============================================================================

File Location: laplms/laplms/utils/merge_students.py

PURPOSE:
    Merge duplicate student records based on phone numbers while:
    - Preserving all enrollment history
    - Maintaining data integrity
    - Converting names to proper Camel Case
    - Cleaning up all related child records

USAGE:
    # From Frappe console
    bench --site your-site console
    
    # Import and use
    from laplms.utils.merge_students import (
        merge_duplicate_students,
        preview_duplicates
    )
    
    # Preview duplicates
    preview_duplicates(limit=10)
    
    # Dry run (no changes)
    result = merge_duplicate_students(dry_run=True)
    
    # Actual merge
    result = merge_duplicate_students(dry_run=False)

==============================================================================
"""

import frappe
from frappe.utils import getdate
from fuzzywuzzy import fuzz
from typing import List, Dict, Set, Tuple


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def names_are_really_similar(name1: str, name2: str, strict: bool = True) -> bool:
    """
    Check if two names are similar enough to be considered the same person.
    
    Args:
        name1: First name to compare
        name2: Second name to compare
        strict: If True, uses stricter matching for first names
    
    Returns:
        bool: True if names are similar enough to merge
    
    Logic:
        - Exact match: Returns True
        - Substring match: Returns True (handles "Nithun" vs "Nithun Dev")
        - Fuzzy match: Uses token set ratio with first name validation
        - First name check: Prevents merging "Nithin" vs "Nithun" (different people)
    
    Examples:
        >>> names_are_really_similar("Nithun Dev", "Nithun")
        True
        >>> names_are_really_similar("Nithin Kumar", "Nithun Kumar")
        False
        >>> names_are_really_similar("John Smith", "john smith")
        True
    """
    name1_clean = name1.strip().lower()
    name2_clean = name2.strip().lower()

    # Quick exact match
    if name1_clean == name2_clean:
        return True

    # Substring match (e.g., "nithun" vs "nithun dev")
    if name1_clean in name2_clean or name2_clean in name1_clean:
        return True

    # Token similarity for full names
    ratio = fuzz.token_set_ratio(name1_clean, name2_clean)

    # First-word similarity check (prevents merging different people)
    words1 = name1_clean.split()
    words2 = name2_clean.split()
    
    if not words1 or not words2:
        return False
    
    first1 = words1[0]
    first2 = words2[0]

    # Only allow if first names are very close (≥90%) or identical
    first_ratio = fuzz.ratio(first1, first2)
    
    if strict:
        # Strict mode: First names must be exact or 90%+ similar
        if first1 == first2 or first_ratio >= 90:
            return ratio >= 85  # Full-name match threshold
        return False
    else:
        # Lenient mode: Allow more variation
        return ratio >= 80


def to_camel_case(text: str) -> str:
    """
    Convert a name to proper Camel Case.
    
    Args:
        text: Name to convert
    
    Returns:
        str: Properly formatted name
    
    Rules:
        - Keeps initials with periods uppercase (e.g., 'T.' stays 'T.')
        - Capitalizes first letter of each word
        - Lowercases remaining letters
    
    Examples:
        >>> to_camel_case("nithun dev")
        "Nithun Dev"
        >>> to_camel_case("T. KUMAR")
        "T. Kumar"
        >>> to_camel_case("JOHN SMITH")
        "John Smith"
    """
    if not text:
        return ""
    
    words = text.strip().split()
    new_words = []

    for w in words:
        if len(w) == 2 and w[1] == ".":  # Initial like 'T.'
            new_words.append(w[0].upper() + ".")
        elif w:  # Handle empty strings
            new_words.append(w[0].upper() + w[1:].lower())
    
    return " ".join(new_words)


def get_enrollment_key(enrollment: Dict) -> Tuple:
    """
    Create a unique key for an enrollment to detect duplicates.
    
    Args:
        enrollment: Enrollment record dictionary
    
    Returns:
        tuple: Unique identifier for the enrollment
    """
    return (
        enrollment.get("batch"),
        enrollment.get("course"),
        enrollment.get("grade"),
        enrollment.get("date_of_joining"),
        enrollment.get("school")
    )


# ==============================================================================
# MAIN MERGE FUNCTION
# ==============================================================================

@frappe.whitelist()
def merge_duplicate_students(
    dry_run: bool = True,
    batch_size: int = 50,
    strict_name_matching: bool = True
) -> Dict:
    """
    Merge duplicate students based on phone numbers with optimized performance.
    
    Args:
        dry_run: If True, only shows what would be merged without making changes
        batch_size: Number of phone groups to process before committing
        strict_name_matching: If True, uses strict first-name validation
    
    Returns:
        dict: Summary of merge operations
        
    Process Flow:
        Step 1: Find all duplicate phone numbers
        Step 2: For each phone number, group similar names
        Step 3: Select primary student (latest joined)
        Step 4: Merge enrollments from duplicates to primary
        Step 5: Delete linked child records
        Step 6: Delete duplicate students
        Step 7: Commit in batches
    """
    
    # Convert string 'True'/'False' to boolean (for web requests)
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in ('true', '1', 'yes')
    if isinstance(strict_name_matching, str):
        strict_name_matching = strict_name_matching.lower() in ('true', '1', 'yes')
    if isinstance(batch_size, str):
        batch_size = int(batch_size)
    
    print("=" * 80)
    print("STUDENT DUPLICATE MERGER - LAPLMS")
    print("=" * 80)
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE RUN (will modify data)'}")
    print(f"Batch Size: {batch_size}")
    print(f"Strict Name Matching: {strict_name_matching}")
    print("=" * 80)
    
    # Statistics tracking
    stats = {
        "duplicate_phones": 0,
        "students_processed": 0,
        "students_merged": 0,
        "enrollments_moved": 0,
        "records_deleted": {
            "backend_students": 0,
            "engagement_states": 0,
            "stage_progress": 0,
            "learning_states": 0,
            "onboarding_progress": 0,
            "duplicate_students": 0
        },
        "names_fixed": 0,
        "errors": []
    }
    
    try:
        # ========================================================================
        # STEP 1: FIND DUPLICATE PHONE NUMBERS
        # ========================================================================
        frappe.publish_realtime(
            "merge_progress",
            {"message": "Finding duplicate phone numbers...", "progress": 0},
            user=frappe.session.user
        )
        
        print("\n📱 STEP 1: Finding duplicate phone numbers...")
        
        duplicates = frappe.db.sql("""
            SELECT phone, COUNT(*) AS cnt
            FROM `tabStudent`
            WHERE phone IS NOT NULL 
              AND phone <> ''
              AND phone <> '0'
            GROUP BY phone
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """, as_dict=True)
        
        stats["duplicate_phones"] = len(duplicates)
        print(f"   Found {len(duplicates)} duplicate phone numbers")
        
        if len(duplicates) == 0:
            print("   ✅ No duplicates found. Exiting.")
            return stats
        
        # ========================================================================
        # STEP 2-7: PROCESS EACH DUPLICATE PHONE GROUP
        # ========================================================================
        batch_counter = 0
        total_groups = len(duplicates)
        
        for idx, d in enumerate(duplicates, 1):
            # Publish progress
            progress = int((idx / total_groups) * 100)
            frappe.publish_realtime(
                "merge_progress",
                {
                    "message": f"Processing {idx}/{total_groups} phone groups...",
                    "progress": progress
                },
                user=frappe.session.user
            )
            
            print(f"\n{'─' * 80}")
            print(f"Processing {idx}/{len(duplicates)} | Phone: {d.phone} ({d.cnt} students)")
            print(f"{'─' * 80}")
            
            try:
                result = process_duplicate_phone_group(
                    phone=d.phone,
                    dry_run=dry_run,
                    strict_name_matching=strict_name_matching
                )
                
                # Update statistics
                stats["students_processed"] += result["students_processed"]
                stats["students_merged"] += result["students_merged"]
                stats["enrollments_moved"] += result["enrollments_moved"]
                stats["names_fixed"] += result["names_fixed"]
                
                for key in stats["records_deleted"]:
                    stats["records_deleted"][key] += result["records_deleted"].get(key, 0)
                
                # Commit in batches
                batch_counter += 1
                if not dry_run and batch_counter >= batch_size:
                    frappe.db.commit()
                    print(f"\n💾 Committed batch of {batch_counter} phone groups")
                    batch_counter = 0
                    
            except Exception as e:
                error_msg = f"Error processing phone {d.phone}: {str(e)}"
                print(f"   ❌ {error_msg}")
                stats["errors"].append(error_msg)
                frappe.log_error(error_msg, "Student Merge Error")
                
                if not dry_run:
                    frappe.db.rollback()
                    print("   🔄 Rolled back transaction for this group")
        
        # Final commit
        if not dry_run and batch_counter > 0:
            frappe.db.commit()
            print(f"\n💾 Final commit of {batch_counter} phone groups")
        
        # ========================================================================
        # PRINT SUMMARY
        # ========================================================================
        print("\n" + "=" * 80)
        print("MERGE SUMMARY")
        print("=" * 80)
        print(f"Duplicate Phone Numbers: {stats['duplicate_phones']}")
        print(f"Students Processed: {stats['students_processed']}")
        print(f"Students Merged: {stats['students_merged']}")
        print(f"Enrollments Moved: {stats['enrollments_moved']}")
        print(f"Names Fixed (Camel Case): {stats['names_fixed']}")
        print(f"\nRecords Deleted:")
        for key, value in stats['records_deleted'].items():
            print(f"  - {key.replace('_', ' ').title()}: {value}")
        
        if stats["errors"]:
            print(f"\n⚠️  Errors Encountered: {len(stats['errors'])}")
            for error in stats["errors"][:10]:  # Show first 10 errors
                print(f"  - {error}")
        
        print("=" * 80)
        
        if dry_run:
            print("\n✅ DRY RUN COMPLETE - No changes were made")
            print("   Run with dry_run=False to apply changes")
        else:
            print("\n✅ MERGE COMPLETE - Changes saved to database")
        
        # Publish completion
        frappe.publish_realtime(
            "merge_progress",
            {
                "message": "Merge complete!",
                "progress": 100,
                "stats": stats
            },
            user=frappe.session.user
        )
        
        return stats
        
    except Exception as e:
        error_msg = f"FATAL ERROR: {str(e)}"
        print(f"\n❌ {error_msg}")
        frappe.log_error(error_msg, "Student Merge Fatal Error")
        
        if not dry_run:
            frappe.db.rollback()
            print("🔄 All changes rolled back")
        
        stats["errors"].append(error_msg)
        return stats


# ==============================================================================
# PROCESS SINGLE PHONE GROUP
# ==============================================================================

def process_duplicate_phone_group(
    phone: str,
    dry_run: bool,
    strict_name_matching: bool
) -> Dict:
    """
    Process all students with the same phone number.
    
    Args:
        phone: Phone number to process
        dry_run: If True, only simulate the merge
        strict_name_matching: Use strict name matching rules
    
    Returns:
        dict: Statistics for this phone group
    """
    
    stats = {
        "students_processed": 0,
        "students_merged": 0,
        "enrollments_moved": 0,
        "names_fixed": 0,
        "records_deleted": {
            "backend_students": 0,
            "engagement_states": 0,
            "stage_progress": 0,
            "learning_states": 0,
            "onboarding_progress": 0,
            "duplicate_students": 0
        }
    }
    
    # ========================================================================
    # STEP 2: GET ALL STUDENTS WITH THIS PHONE
    # ========================================================================
    students = frappe.get_all(
        "Student",
        filters={"phone": phone},
        fields=["name", "name1", "joined_on"],
        order_by="joined_on DESC"  # Latest first
    )
    
    stats["students_processed"] = len(students)
    
    if len(students) < 2:
        print("   ℹ️  Only one student with this phone, skipping")
        return stats
    
    print(f"   Found {len(students)} students:")
    for s in students:
        print(f"      - {s.name1} (ID: {s.name}, Joined: {s.joined_on})")
    
    # ========================================================================
    # STEP 3: GROUP BY SIMILAR NAMES
    # ========================================================================
    processed = set()
    
    for i, base in enumerate(students):
        if base["name"] in processed:
            continue
        
        # Find all students with similar names
        similar_group = [base]
        for j, other in enumerate(students):
            if i == j or other["name"] in processed:
                continue
            
            if names_are_really_similar(
                base["name1"], 
                other["name1"], 
                strict=strict_name_matching
            ):
                similar_group.append(other)
                processed.add(other["name"])
        
        # Only merge if more than one truly similar record
        if len(similar_group) < 2:
            print(f"   ℹ️  {base['name1']}: No similar names found, skipping")
            continue
        
        # Sort by join date (latest = primary)
        similar_group.sort(
            key=lambda x: getdate(x.get("joined_on") or "1900-01-01"), 
            reverse=True
        )
        
        primary = similar_group[0]
        duplicates_to_remove = similar_group[1:]
        
        print(f"\n   👥 Merging group:")
        print(f"      PRIMARY: {primary['name1']} (ID: {primary['name']}, Joined: {primary['joined_on']})")
        print(f"      DUPLICATES: {len(duplicates_to_remove)}")
        for dup in duplicates_to_remove:
            print(f"         - {dup['name1']} (ID: {dup['name']}, Joined: {dup['joined_on']})")
        
        # ====================================================================
        # STEP 4: MERGE ENROLLMENTS
        # ====================================================================
        merge_result = merge_enrollments(primary, duplicates_to_remove, dry_run)
        stats["enrollments_moved"] += merge_result["enrollments_moved"]
        stats["names_fixed"] += merge_result["names_fixed"]
        
        # ====================================================================
        # STEP 5: DELETE CHILD RECORDS
        # ====================================================================
        for dup in duplicates_to_remove:
            delete_result = delete_linked_records(dup["name"], dry_run)
            
            for key in stats["records_deleted"]:
                stats["records_deleted"][key] += delete_result.get(key, 0)
            
            stats["students_merged"] += 1
    
    return stats


# ==============================================================================
# ENROLLMENT MERGING
# ==============================================================================

def merge_enrollments(
    primary: Dict,
    duplicates: List[Dict],
    dry_run: bool
) -> Dict:
    """
    Merge enrollments from duplicate students to primary student.
    
    Args:
        primary: Primary student dictionary
        duplicates: List of duplicate student dictionaries
        dry_run: If True, only simulate the merge
    
    Returns:
        dict: Statistics for enrollment merge
    """
    
    stats = {
        "enrollments_moved": 0,
        "names_fixed": 0
    }
    
    # Load primary student document
    primary_doc = frappe.get_doc("Student", primary["name"])
    
    # Fix name to Camel Case
    proper_name = to_camel_case(primary_doc.name1)
    if primary_doc.name1 != proper_name:
        print(f"      🔤 Fixing name: '{primary_doc.name1}' → '{proper_name}'")
        if not dry_run:
            primary_doc.name1 = proper_name
        stats["names_fixed"] += 1
    
    # Get existing enrollments
    existing_enrollments = set()
    for e in primary_doc.get("enrollments") or []:
        key = get_enrollment_key(e)
        existing_enrollments.add(key)
    
    print(f"      📚 Primary has {len(existing_enrollments)} existing enrollments")
    
    # Process each duplicate
    for dup in duplicates:
        dup_doc = frappe.get_doc("Student", dup["name"])
        added = 0
        skipped = 0
        
        for enroll in dup_doc.get("enrollments") or []:
            key = get_enrollment_key(enroll)
            
            if key not in existing_enrollments:
                if not dry_run:
                    primary_doc.append("enrollments", {
                        "batch": enroll.batch,
                        "course": enroll.course,
                        "grade": enroll.grade,
                        "date_of_joining": enroll.date_of_joining,
                        "school": enroll.school
                    })
                existing_enrollments.add(key)
                added += 1
            else:
                skipped += 1
        
        if added > 0:
            print(f"         ➕ From {dup['name1']}: Added {added} enrollments, Skipped {skipped} duplicates")
            stats["enrollments_moved"] += added
        else:
            print(f"         ℹ️  From {dup['name1']}: No new enrollments")
    
    # Save primary document
    if (stats["enrollments_moved"] > 0 or stats["names_fixed"] > 0) and not dry_run:
        primary_doc.save(ignore_permissions=True)
        print(f"      ✅ Saved primary student: {primary_doc.name}")
    
    return stats


# ==============================================================================
# CHILD RECORD DELETION
# ==============================================================================

def delete_linked_records(student_id: str, dry_run: bool) -> Dict:
    """
    Delete all child records linked to a duplicate student.
    
    Args:
        student_id: Student ID to delete records for
        dry_run: If True, only simulate the deletion
    
    Returns:
        dict: Count of deleted records
    """
    
    stats = {
        "backend_students": 0,
        "engagement_states": 0,
        "stage_progress": 0,
        "learning_states": 0,
        "onboarding_progress": 0,
        "duplicate_students": 0
    }
    
    print(f"\n      🗑️  Deleting linked records for: {student_id}")
    
    # Backend Students (bulk delete for efficiency)
    if not dry_run:
        frappe.db.sql("""
            DELETE FROM `tabBackend Students`
            WHERE student_id = %s
        """, (student_id,))
        count = frappe.db.sql("""
            SELECT ROW_COUNT() as count
        """, as_dict=True)[0].get('count', 0)
        stats["backend_students"] = count
    else:
        count = frappe.db.count("Backend Students", {"student_id": student_id})
        stats["backend_students"] = count
    
    if stats["backend_students"] > 0:
        print(f"         ✓ Backend Students: {stats['backend_students']}")
    
    # EngagementState
    linked_states = frappe.get_all(
        "EngagementState",
        filters={"student": student_id},
        fields=["name"]
    )
    stats["engagement_states"] = len(linked_states)
    if not dry_run:
        for state in linked_states:
            frappe.delete_doc("EngagementState", state["name"], ignore_permissions=True, force=True)
    if stats["engagement_states"] > 0:
        print(f"         ✓ Engagement States: {stats['engagement_states']}")
    
    # StudentStageProgress
    linked_progress = frappe.get_all(
        "StudentStageProgress",
        filters={"student": student_id},
        fields=["name"]
    )
    stats["stage_progress"] = len(linked_progress)
    if not dry_run:
        for progress in linked_progress:
            frappe.delete_doc("StudentStageProgress", progress["name"], ignore_permissions=True, force=True)
    if stats["stage_progress"] > 0:
        print(f"         ✓ Stage Progress: {stats['stage_progress']}")
    
    # LearningState
    linked_learning = frappe.get_all(
        "LearningState",
        filters={"student": student_id},
        fields=["name"]
    )
    stats["learning_states"] = len(linked_learning)
    if not dry_run:
        for state in linked_learning:
            frappe.delete_doc("LearningState", state["name"], ignore_permissions=True, force=True)
    if stats["learning_states"] > 0:
        print(f"         ✓ Learning States: {stats['learning_states']}")
    
    # StudentOnboardingProgress
    linked_onboarding = frappe.get_all(
        "StudentOnboardingProgress",
        filters={"student": student_id},
        fields=["name"]
    )
    stats["onboarding_progress"] = len(linked_onboarding)
    if not dry_run:
        for progress in linked_onboarding:
            frappe.delete_doc("StudentOnboardingProgress", progress["name"], ignore_permissions=True, force=True)
    if stats["onboarding_progress"] > 0:
        print(f"         ✓ Onboarding Progress: {stats['onboarding_progress']}")
    
    # Delete the duplicate student itself
    if not dry_run:
        frappe.delete_doc("Student", student_id, ignore_permissions=True, force=True)
    stats["duplicate_students"] = 1
    print(f"         ✓ Deleted student: {student_id}")
    
    return stats


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

@frappe.whitelist()
def preview_duplicates(limit: int = 10) -> Dict:
    """
    Preview duplicate students without making any changes.
    
    Args:
        limit: Number of duplicate phone groups to preview
    
    Returns:
        dict: Preview data
    """
    
    if isinstance(limit, str):
        limit = int(limit)
    
    print("=" * 80)
    print("DUPLICATE STUDENTS PREVIEW")
    print("=" * 80)
    
    duplicates = frappe.db.sql("""
        SELECT phone, COUNT(*) AS cnt
        FROM `tabStudent`
        WHERE phone IS NOT NULL 
          AND phone <> ''
          AND phone <> '0'
        GROUP BY phone
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,), as_dict=True)
    
    print(f"\nShowing top {limit} duplicate phone numbers:\n")
    
    preview_data = []
    
    for idx, d in enumerate(duplicates, 1):
        students = frappe.get_all(
            "Student",
            filters={"phone": d.phone},
            fields=["name", "name1", "joined_on"],
            order_by="joined_on DESC"
        )
        
        print(f"{idx}. Phone: {d.phone} ({d.cnt} students)")
        student_list = []
        for s in students:
            print(f"   - {s.name1} (ID: {s.name}, Joined: {s.joined_on or 'Unknown'})")
            student_list.append({
                "name": s.name,
                "name1": s.name1,
                "joined_on": s.joined_on
            })
        print()
        
        preview_data.append({
            "phone": d.phone,
            "count": d.cnt,
            "students": student_list
        })
    
    print("=" * 80)
    
    return {
        "total_duplicate_phones": len(duplicates),
        "preview": preview_data
    }