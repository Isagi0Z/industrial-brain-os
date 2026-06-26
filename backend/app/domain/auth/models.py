from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Permission:
    id: str
    name: str
    description: Optional[str] = None


@dataclass
class Role:
    id: str
    name: str
    permissions: List[Permission] = field(default_factory=list)


@dataclass
class User:
    id: str
    email: str
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = True
    roles: List[Role] = field(default_factory=list)

    def has_permission(self, permission_name: str) -> bool:
        if not self.is_active:
            return False
        for role in self.roles:
            for perm in role.permissions:
                if perm.name == permission_name:
                    return True
        return False
