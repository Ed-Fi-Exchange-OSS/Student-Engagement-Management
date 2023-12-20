SELECT cal.schoolid
        , cal.schoolyear
        , cd.date
        , e.nameofinstitution
        , cdce.calendareventdescriptorid
        , d.shortdescription as eventdescription
FROM edfi.calendar as cal
JOIN edfi.calendardate as cd 
    ON cal.CalendarCode = cd.calendarcode
        AND cal.schoolyear = cd.schoolyear
JOIN edfi.calendardatecalendarevent cdce
    ON cal.CalendarCode = cdce.calendarcode
        AND cal.schoolid = cdce.schoolid
        AND cal.schoolyear = cdce.schoolyear
        AND cd.date = cdce.date
JOIN edfi.educationorganization e
    ON e.educationorganizationid = cal.schoolid
JOIN edfi.descriptor d
    ON cdce.calendareventdescriptorid = d.descriptorid