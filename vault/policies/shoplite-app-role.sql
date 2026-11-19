CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';
GRANT SELECT, INSERT ON orders TO "{{name}}";
GRANT USAGE ON SEQUENCE orders_id_seq TO "{{name}}";
