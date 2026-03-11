
from django.db.models import JSONField, Lookup


@JSONField.register_lookup
class JSONValueContains(Lookup):
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
class JSONValueExact(Lookup):
    """
    Custom lookup for exact matching within JSONB values using the jsonb_values_concat function.

    Usage:
        ObjectValue.objects.filter(values__jsonb_vexact='exact_term')

    This will search for exact 'exact_term' within all values in the JSONB field using =.
    """

    lookup_name = "jsonb_vexact"
    
    def process_rhs(self, compiler, connection):
        rhs, params = super().process_rhs(compiler, connection)
        params[0] = f"%{params[0]}%"
        return rhs, params

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)

        sql = f"jsonb_values_concat({lhs}) ILIKE {rhs}"
        return sql, lhs_params + rhs_params