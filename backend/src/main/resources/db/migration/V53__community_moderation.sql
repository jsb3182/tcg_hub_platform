ALTER TABLE board_post ADD COLUMN hidden boolean NOT NULL DEFAULT false;
ALTER TABLE post_comment ADD COLUMN hidden boolean NOT NULL DEFAULT false;

CREATE INDEX community_post_timeline ON board_post(id DESC) WHERE NOT hidden;
CREATE INDEX community_comment_timeline ON post_comment(post_id,id) WHERE NOT hidden;
CREATE INDEX community_comment_replies ON post_comment(post_id,parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX community_report_queue ON abuse_report(status,id DESC);
