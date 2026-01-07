import frappe

# Update teacher_batch for ALL teachers
def update_all_teachers_batch():
    teachers = frappe.get_all(
        "Teacher", 
        filters={"school_id": ["!=", ""]}, 
        fields=["name", "first_name", "last_name", "school_id"]
    )
    
    print(f"Found {len(teachers)} teachers to process\n")
    
    updated = 0
    skipped = 0
    no_batch = 0
    
    for teacher in teachers:
        teacher_doc = frappe.get_doc("Teacher", teacher.name)
        
        # Get batch onboardings for this school
        batch_onboardings = frappe.get_all(
            "Batch onboarding",
            filters={"school": teacher_doc.school_id},
            fields=["name", "batch", "creation"],
            order_by="creation desc"
        )
        
        if not batch_onboardings:
            no_batch += 1
            continue
        
        # Find the first active batch
        batch_found = False
        for bo in batch_onboardings:
            batch = frappe.get_doc("Batch", bo.batch)
            
            if batch.active:
                teacher_doc.teacher_batch = batch.name
                teacher_doc.save()
                updated += 1
                batch_found = True
                print(f"✓ {teacher.name} → {batch.name}")
                break
        
        if not batch_found:
            skipped += 1
    
    frappe.db.commit()
    
    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Updated: {updated}")
    print(f"  No active batch: {skipped}")
    print(f"  No batch onboarding: {no_batch}")
    print(f"{'='*50}")

# Run it
#update_all_teachers_batch()