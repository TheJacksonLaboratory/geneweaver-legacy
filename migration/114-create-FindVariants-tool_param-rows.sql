INSERT INTO odestatic.tool_param
VALUES
('FindVariants',
 'FindVariants_Path',
 'Choose the path of finding the variants',
 '{html_checkboxes name=$p.tp_name options=$p.tp_options output=$p.tp_options selected=$p._cur_val separator="<br />"}',
 'using eQTL',
 '["using eQTL", "using Transcript"]',
 'checkbox',
 TRUE
 );

INSERT INTO odestatic.tool_param
VALUES
('FindVariants',
 'FindVariants_Species',
 'Starting and ending species',
 '{html_radios name=$p.tp_name values=$p.tp_options output=$p.tp_options selected=$p._cur_val separator="<br />"}',
 'Human to Mouse',
 '["Human to Mouse", "Mouse to Human"]',
 'radio',
 TRUE
 );