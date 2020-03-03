SELECT username, killer, (SELECT COUNT(*) FROM "bhvr"."dbd_player_match" WHERE killed AND match_id=b.match_id) AS kill_count
FROM "bhvr"."dbd_player_match" AS a 
INNER JOIN "bhvr"."dbd_match_id" AS b 
ON a.match_id=b.match_id 
WHERE a.match_id=b.match_id AND killer <> '' GROUP BY username, killer, b.match_id