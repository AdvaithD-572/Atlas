ALTER TABLE chunks ADD COLUMN page_number integer CHECK(page_number BETWEEN 1 AND 200);
ALTER TABLE chunks ADD COLUMN heading text CHECK(length(heading) <= 512);
