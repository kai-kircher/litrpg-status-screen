-- Cleanup script to remove the book overview page that was incorrectly scraped as chapter 1
-- This script deletes the entry and renumbers all subsequent chapters

BEGIN;

-- First, let's check what we're about to delete
SELECT order_index, chapter_number, url
FROM chapters
WHERE url LIKE '%/book/%'
ORDER BY order_index;

-- Delete the book overview entry (and cascade to any related raw_events)
DELETE FROM chapters WHERE url LIKE '%/book/%';

-- Renumber the remaining chapters to be sequential starting from 1
-- This uses a window function to reassign order_index values
WITH renumbered AS (
  SELECT
    id,
    ROW_NUMBER() OVER (ORDER BY order_index) as new_order_index
  FROM chapters
)
UPDATE chapters
SET order_index = renumbered.new_order_index
FROM renumbered
WHERE chapters.id = renumbered.id;

-- Verify the results
SELECT order_index, chapter_number, url
FROM chapters
ORDER BY order_index
LIMIT 10;

COMMIT;
