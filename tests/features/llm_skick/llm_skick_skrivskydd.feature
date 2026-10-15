Feature: Skrivskyddat konto (PROTONMAIL_READ_ONLY)
  Som användare som låter en LLM läsa min e-post
  vill jag kunna göra kontot skrivskyddat för servern
  så att en skenande loop eller en promptinjektion inte kan flytta, radera,
  märka, skapa utkast eller skicka något.

  Scenario: Läsande verktyg fungerar som vanligt när kontot är skrivskyddat
    Given servern körs med inställningen "read_only" satt till "true"
    And Bridge har mappen "INBOX"
    When LLM:en anropar verktyget "list_mailboxes"
    Then ska verktyget svara utan fel

  Scenario Outline: Skrivande verktyg vägras innan Bridge kontaktas
    Given servern körs med inställningen "read_only" satt till "true"
    When LLM:en anropar verktyget "<verktyg>"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_READ_ONLY"
    And ska Bridge inte ha kontaktats

    Examples:
      | verktyg        |
      | move_email     |
      | delete_email   |
      | mark_email_read |
      | flag_email     |
      | add_label      |
      | create_folder  |
      | rename_folder  |
      | create_draft   |
      | update_draft   |
      | send_draft     |
      | send_email     |
      | reply_to_email |
      | forward_email  |

  Scenario: IMAP-klienten vägrar skrivningar även om ett verktyg skulle glömmas
    Given en IMAP-klient för ett konto med inställningen "read_only" satt till "true"
    When koden direkt i IMAP-klienten flyttar UID "5" i "INBOX" till "Archive"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_READ_ONLY"
    And ska Bridge inte ha kontaktats

  Scenario: SMTP-klienten vägrar skick även om ett verktyg skulle glömmas
    Given en SMTP-klient för ett konto med inställningen "read_only" satt till "true"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_READ_ONLY"
    And ska Bridge inte ha kontaktats

  Scenario: Utan inställningen skickas mejl som förut
    Given en SMTP-klient för ett konto utan begränsningar
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se"
    Then ska mejlet ha skickats till "anna@exempel.se"
