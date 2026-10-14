Feature: Inställningar hittas oavsett arbetskatalog
  Som användare som startar servern med uv run --project från en annan katalog
  vill jag att projektets .env läses ändå
  så att servern inte dör vid start med ett valideringsfel som klienten aldrig ser.

  Scenario: Projektrotens .env läses när servern startas från en annan katalog
    Given en projektkatalog vars .env har användarnamnet "rot@proton.me"
    And att arbetskatalogen är en annan katalog utan .env
    When inställningarna laddas
    Then ska användarnamnet vara "rot@proton.me"

  Scenario: En .env i arbetskatalogen har företräde framför projektrotens
    Given en projektkatalog vars .env har användarnamnet "rot@proton.me"
    And att arbetskatalogen har en .env med användarnamnet "cwd@proton.me"
    When inställningarna laddas
    Then ska användarnamnet vara "cwd@proton.me"
