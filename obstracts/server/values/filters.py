
from django.db.models import JSONField, Lookup


@JSONField.register_lookup
class JSONValueTrigram(Lookup):
    """
    Custom lookup for searching within JSONB values using the jsonb_values_concat function with trigram matching.

    Usage:
        ObjectValue.objects.filter(values__jsonb_trg='search_term')

    This will search for 'search_term' within all values in the JSONB field using trigram similarity (%).
    """

    lookup_name = "jsonb_trg"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)

        sql = f"jsonb_values_concat({lhs}) %% %s"
        return sql, lhs_params + rhs_params


@JSONField.register_lookup
class JSONValueContains(Lookup):
    """
    Custom lookup for substring matching within concatenated JSONB values using the jsonb_values_concat function.

    Usage:
        ObjectValue.objects.filter(values__jsonb_vcontains='search_term')

    This will search for 'search_term' within the concatenated values in the JSONB field using ILIKE.
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

        # Use jsonb_each_text to iterate over key-value pairs and check if any value matches exactly
        sql = f"EXISTS (SELECT 1 FROM jsonb_each_text({lhs}) WHERE value = %s)"
        return sql, lhs_params + rhs_params