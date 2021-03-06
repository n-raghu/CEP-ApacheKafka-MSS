import graphene
from graphene import relay
from model import db_session
from graphene_sqlalchemy import SQLAlchemyObjectType, SQLAlchemyConnectionField
from model import Department as DepartmentModel, Employee as EmployeeModel


class Department(SQLAlchemyObjectType):
    class Meta:
        model = DepartmentModel
        interfaces = (relay.Node, )


class Employee(SQLAlchemyObjectType):
    class Meta:
        model = EmployeeModel
        interfaces = (relay.Node, )


class Query(graphene.ObjectType):
    node = relay.Node.Field()
    # Allows sorting over multiple columns, by default over the primary key
    all_employees = SQLAlchemyConnectionField(Employee)
    # Disable sorting over this field
    all_departments = SQLAlchemyConnectionField(Department, sort=None)


schema = graphene.Schema(query=Query)
