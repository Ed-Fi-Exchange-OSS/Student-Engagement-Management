
select distinct
    {{ dbt_utils.generate_surrogate_key([
        'sections.course_offering_reference.school_id',
        'sections.course_offering_reference.school_year',
        'sections.course_offering_reference.session_name',
        'sections.course_offering_reference.local_course_code',
        'sections.section_identifier'
    ]) }}                                                       as section_key,
    {{ dbt_utils.generate_surrogate_key([
        'schools.school_id',
        'schools.school_year'
    ]) }}                                                       as school_key,
    sections.section_identifier                                 as section_identifier,
    coalesce(
        sections.section_name,
        concat(
            course_offering_reference.local_course_code, '-',
            sessions.session_name
        )
    )                                                           as section_name,
    sessions.session_name                                       as session_name,
    course_offering_reference.local_course_code                 as local_course_code,
    courses.course_title                                        as course_title,
    course_offerings.session_reference.school_year              as school_year,
from {{ ref('stg_edfi_sections') }} sections
left join unnest(sections.class_periods) as class_period
left join {{ ref('stg_edfi_schools') }} schools
    on sections.course_offering_reference.school_id = schools.school_id
    and sections.course_offering_reference.school_year =  schools.school_year
left join {{ ref('stg_edfi_course_offerings') }} course_offerings
    on sections.school_year = course_offerings.school_year
    and course_offerings.local_course_code = sections.course_offering_reference.local_course_code
    and course_offerings.school_reference.school_id = sections.course_offering_reference.school_id
    and course_offerings.session_reference.school_year = sections.course_offering_reference.school_year
    and course_offerings.session_reference.session_name = sections.course_offering_reference.session_name
left join {{ ref('stg_edfi_courses') }} courses
    on course_offerings.school_year = courses.school_year
    and courses.course_code = course_offerings.course_reference.course_code
    and courses.education_organization_reference.education_organization_id = course_offerings.course_reference.education_organization_id
left join {{ ref('stg_edfi_sessions') }} sessions
    on course_offerings.session_reference.school_id = sessions.school_reference.school_id
    and course_offerings.session_reference.school_year = sessions.school_year_type_reference.school_year
    and course_offerings.session_reference.session_name = sessions.session_name
