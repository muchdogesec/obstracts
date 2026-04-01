
from django.db.models import JSONField, Lookup
from django.db.models import Func, CharField

@JSONField.register_lookup
class JSONValueContains(Lookup):
    """
    Custom lookup for substring matching within concatenated JSONB values
    using the jsonb_values_concat function.

    Usage:
        ObjectValue.objects.filter(values__jsonb_vcontains='search_term')

    This will search for 'search_term' within the concatenated JSONB values
    using ILIKE.
    """

    lookup_name = "jsonb_vcontains"

    def process_rhs(self, compiler, connection):
        rhs, params = super().process_rhs(compiler, connection)
        params[0] = f"%{params[0]}%"
        return rhs, params

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)

        sql = f"jsonb_values_concat({lhs}) ILIKE %s"
        return sql, lhs_params + rhs_params


@JSONField.register_lookup
class JSONValueExact(Lookup):
    """
    Custom lookup for exact matching of a single value within JSONB values.

    Usage:
        ObjectValue.objects.filter(values__jsonb_vexact='exact_value')

    This will check if the exact value exists as one of the values in the JSONB field.
    """

    lookup_name = "jsonb_vexact"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        sql = f"jsonb_values_list({lhs}) @> ARRAY[LOWER(%s)]"
        return sql, lhs_params + rhs_params

class DictFirstValue(Func):
    """
    Returns the first value from a JSONB array.
    """
    function = "jsonb_first_value"
    output_field = CharField()
