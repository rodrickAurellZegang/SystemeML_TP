from feast import Entity

user = Entity(
    name="user",
    join_keys=["user_id"],
    description="L'identifiant de l'utilisateur de StreamFlow",
)