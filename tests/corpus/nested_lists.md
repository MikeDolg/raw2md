# Structure and processing order

The section checks that nested lists survive conversion: bulleted lists with
several nesting levels, numbered lists, and mixed ones. Nested lists touch the
§6 normalisation of blank lines around markup blocks.

## Bulleted lists

Incoming documents fall into three categories:

- Paper originals
  - Contracts and certificates
    - Bilateral
    - Multilateral
  - Waybills and invoices
- Electronic copies
  - Received by mail
  - Loaded from the system
- Archive material

## Numbered lists

The processing order of one document:

1. Check the file format.
2. Choose the conversion engine.
3. Start the conversion:
   1. Prepare the working folder.
   2. Call the engine.
   3. Write the log.
4. Grade the result.
5. Save and close.

## Mixed lists

A three-level mixed nesting: bulleted → numbered → bulleted.

- Urgent material
  1. Payment orders
     - electronic transfer
     - paper order
  2. Contracts with a deadline
     - main contract
     - appendices
- Planned material
  1. Monthly reports
  2. Technical documentation
- Deferred material
  1. Archive copies
  2. Drafts and sketches

## Lists with long items

Each item below spans several lines, to check that the line wrap does not
break the structure of a nested list during cleaning:

- The first subsection of the archive procedure, which covers the storage
  rules for originals and copies of documents kept for more than five years.
- The second subsection, which describes how documents are destroyed once
  their storage period ends, as the applicable law requires.
- The third subsection, on the rules for handing files to the state archive
  when a department is closed or reorganised.
