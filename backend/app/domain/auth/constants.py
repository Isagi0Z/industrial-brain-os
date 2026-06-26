from enum import Enum


class SystemRole(str, Enum):
    SUPER_ADMIN = "Super Admin"
    ADMINISTRATOR = "Administrator"
    KNOWLEDGE_ENGINEER = "Knowledge Engineer"
    MAINTENANCE_ENGINEER = "Maintenance Engineer"
    OPERATIONS_ENGINEER = "Operations Engineer"
    COMPLIANCE_OFFICER = "Compliance Officer"
    AUDITOR = "Auditor"
    TECHNICIAN = "Technician"
    OPERATOR = "Operator"
    VIEWER = "Viewer"
