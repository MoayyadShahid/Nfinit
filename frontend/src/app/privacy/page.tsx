import { LegalPage, Section } from "@/components/LegalPage";
import { LEGAL } from "@/lib/legal";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy · nfinit",
  description: "What data Nfinit collects, why, who receives it, and your rights.",
};

const { operator, location, contactEmail, privacyOfficer, minimumAge } = LEGAL;
const mail = `mailto:${contactEmail}`;

/** Every service that receives personal data, and what it receives. */
const PROVIDERS: { name: string; purpose: string; data: string }[] = [
  {
    name: "Supabase",
    purpose: "Database and sign-in",
    data: "Your account details, projects, chat history, runs and subscription status",
  },
  {
    name: "Google",
    purpose: "Sign-in with your Google account",
    data: "That you sign in to Nfinit. Google then sends us your name, email address and profile picture",
  },
  {
    name: "OpenRouter",
    purpose: "Sends your requests to the AI model",
    data: "Your prompts, attached images, the current code of your part and the face you selected",
  },
  {
    name: "Anthropic",
    purpose: "Claude AI models that write the CAD code",
    data: "The same data that OpenRouter receives, through OpenRouter",
  },
  {
    name: "Stripe",
    purpose: "Payments and receipts",
    data: "Your email address, card details and the billing details you enter at checkout",
  },
  {
    name: "Vercel",
    purpose: "Hosts the website",
    data: "Technical data such as IP address and pages requested",
  },
  {
    name: "Railway",
    purpose: "Hosts the servers that build your parts",
    data: "Your requests to the servers, and technical data such as IP address",
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      summary={
        <ul>
          <li>The local open-source workspace stores projects and original STL files on your machine. Prompts, reference images and CAD tool results are sent through your selected agent to its provider under your account. The hosted-service collection described below applies when you use the hosted deployment.</li>
          <li>
            We collect what we need to run Nfinit: your Google sign-in details, the
            prompts, images and parts you make, and your subscription status.
          </li>
          <li>
            Your prompts and images go to AI model providers so they can write your CAD
            code. Payments go through Stripe. Section 4 lists every service that gets your
            data.
          </li>
          <li>
            We do not sell your data, we do not show ads, we do not use tracking cookies,
            and we do not use your designs to train AI models.
          </li>
          <li>
            You can delete a project in the studio, and delete your whole account on the{" "}
            <Link href="/account" className="underline underline-offset-4">
              Account page
            </Link>
            . To get a copy of your data, email{" "}
            <a href={mail} className="underline underline-offset-4">
              {contactEmail}
            </a>
            .
          </li>
        </ul>
      }
    >
      <Section id="who" title="1. Who we are">
        <p>
          {operator} (&ldquo;Nfinit&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;), based in{" "}
          {location}, runs the Nfinit website and studio and is responsible for your
          personal data. This policy is part of our{" "}
          <Link href="/terms">Terms of Service</Link>.
        </p>
        <p>
          Our privacy officer, {privacyOfficer}, is accountable for how we handle personal
          data. Contact our privacy officer at <a href={mail}>{contactEmail}</a>.
        </p>
      </Section>

      <Section id="collect" title="2. What we collect">
        <h3>Data you give us</h3>
        <ul>
          <li>
            <strong>Account data:</strong> when you sign in with Google, we receive your
            name, email address, profile picture and a Google account ID.
          </li>
          <li>
            <strong>Your content:</strong> the prompts you type, images you attach, faces
            you select and code you edit. We also keep what the Service makes for you: the
            design plan, the CAD code, the 3D part files, a preview image and the history
            of each project.
          </li>
          <li>
            <strong>Messages to us:</strong> what you write when you email us.
          </li>
        </ul>
        <h3>Data we create when you use Nfinit</h3>
        <ul>
          <li>
            <strong>Run records:</strong> each time the AI builds a part, we record the
            request, the model used, the steps it took, the time they took, the number of
            AI tokens used and the cost.
          </li>
          <li>
            <strong>Subscription data:</strong> your Stripe customer ID, subscription
            status and renewal date. We do not receive or keep your full card number.
          </li>
          <li>
            <strong>Technical data:</strong> our hosting providers record technical logs,
            such as IP address, browser type, the pages and actions requested, times and
            errors. We use them to keep the Service working and secure.
          </li>
        </ul>
        <h3>Data stored in your browser</h3>
        <p>
          We use only the cookies and browser storage that the Service needs to work:
        </p>
        <ul>
          <li>sign-in cookies, which keep you signed in;</li>
          <li>your light or dark theme choice;</li>
          <li>the last project you opened, and a run in progress, so a reload can continue it;</li>
          <li>an action you started before checkout, so it can finish after you pay.</li>
        </ul>
        <p>
          We do not use advertising cookies, analytics trackers or social media pixels.
        </p>
      </Section>

      <Section id="use" title="3. How we use your data">
        <ul>
          <li>to sign you in and run your account;</li>
          <li>to generate, build, store and export your parts;</li>
          <li>to process payments and manage your subscription;</li>
          <li>to find and fix errors, measure speed and cost, and prevent abuse;</li>
          <li>to answer your messages and send important notices about the Service; and</li>
          <li>to obey the law and protect our rights.</li>
        </ul>
        <p>
          We send you only emails about your account and the Service, such as receipts and
          notices of changes. We do not send marketing emails unless you agree to receive
          them, and you can stop them at any time.
        </p>
        <p>
          <strong>We do not sell your personal data. We do not show ads.</strong> We do not
          use your content to train AI models. If we ever want to use your content to
          improve the Service in a new way, we will ask for your permission first, and you
          can say no.
        </p>
      </Section>

      <Section id="providers" title="4. Who receives your data">
        <p>
          We share personal data only with the service providers below, and only to run
          Nfinit. They process it for us under their own terms and privacy policies.
        </p>
        <ul className="legal-providers">
          {PROVIDERS.map((provider) => (
            <li key={provider.name}>
              <strong>{provider.name}</strong>: {provider.purpose}.
              <br />
              <span>Receives: {provider.data}.</span>
            </li>
          ))}
        </ul>
        <p>
          If we add a service that receives your personal data, we will add it to this list
          before we use it. We can also share data when the law requires it, to protect
          people&rsquo;s safety or our rights, or as part of a sale or transfer of the
          Service. In a transfer, this policy continues to apply to your data.
        </p>
      </Section>

      <Section id="legal-bases" title="5. Consent and legal bases">
        <p>
          When you create an account and use Nfinit, you consent to the collection, use and
          disclosure of your personal data as this policy describes. You can withdraw your
          consent at any time by deleting your account. We cannot run the Service for you
          without the data it needs.
        </p>
        <p>Where EU or UK data protection law applies, we use your data because:</p>
        <ul>
          <li>
            it is necessary to provide the Service you asked for, under our contract with
            you (account, parts, payments);
          </li>
          <li>
            we have a legitimate interest in keeping the Service secure, fixing errors and
            preventing abuse;
          </li>
          <li>the law requires it (for example, tax records); or</li>
          <li>you gave consent, which you can withdraw at any time.</li>
        </ul>
      </Section>

      <Section id="transfers" title="6. Where your data is processed">
        <p>
          We are in Canada, but we and our service providers store and process your data in
          the United States and possibly in other countries. While your data is in another
          country, it is subject to that country&rsquo;s laws, and its courts, police and
          government can get access to it under those laws.
        </p>
        <p>
          We choose service providers that protect personal data, and we use their
          contracts to require that protection. When we transfer personal data from the EU
          or the UK, we rely on the safeguards that our providers offer, such as the
          European Commission&rsquo;s Standard Contractual Clauses.
        </p>
      </Section>

      <Section id="retention" title="7. How long we keep your data">
        <ul>
          <li>
            <strong>Projects:</strong> until you delete the project or your account. When
            you delete a project, we delete its history, part files and preview image.
          </li>
          <li>
            <strong>Account data and run records:</strong> while your account is open.
          </li>
          <li>
            <strong>Build previews:</strong> the previews shown while a part builds stay in
            server memory for a short time and are not saved.
          </li>
          <li>
            <strong>Account deletion:</strong> when you select{" "}
            <strong>Delete account</strong> on the <Link href="/account">Account page</Link>,
            we cancel your subscription and delete your account and all your data at once.
            If you ask by email instead, we do this within 30 days. Copies in backups are
            deleted when the backups expire.
          </li>
          <li>
            <strong>Payment and tax records:</strong> Stripe and we keep these for as long
            as tax and accounting laws require, even after you close your account.
          </li>
          <li>
            <strong>Technical logs:</strong> for the short period our hosting providers
            keep them.
          </li>
        </ul>
      </Section>

      <Section id="rights" title="8. Your rights and choices">
        <p>You can ask us to:</p>
        <ul>
          <li>tell you what personal data we have about you and give you a copy;</li>
          <li>correct data that is wrong;</li>
          <li>delete your data or your account;</li>
          <li>give you your data in a format that you can move to another service; and</li>
          <li>stop or limit some uses of your data, or withdraw consent.</li>
        </ul>
        <p>
          Email our privacy officer at <a href={mail}>{contactEmail}</a> from the email
          address of your account. We answer within 30 days. We may ask for more information to confirm that the
          request comes from you. We will not treat you differently because you used these
          rights.
        </p>
        <p>
          You can do some of this yourself: delete a project in the studio, cancel your
          subscription with <strong>Manage billing</strong>, and delete your account, both
          on the <Link href="/account">Account page</Link>.
        </p>
        <p>
          <strong>Complaints:</strong> if you are not satisfied with our answer, you can
          complain to the{" "}
          <a href="https://www.priv.gc.ca" rel="noopener" target="_blank">
            Office of the Privacy Commissioner of Canada
          </a>
          . If you live in Quebec, you can also contact the Commission d&rsquo;accès à
          l&rsquo;information du Québec. If you live in the EU or the UK, you can complain
          to your data protection authority.
        </p>
        <p>
          <strong>California residents:</strong> we do not sell or share your personal
          information for cross-context behavioral advertising. Sections 2 to 4 list the
          categories of personal information we collect, where they come from, why we use
          them and who receives them. You have the rights listed above.
        </p>
        <p>
          <strong>Do Not Track:</strong> we do not track you across other websites, so we
          do not change anything when your browser sends a Do Not Track signal.
        </p>
      </Section>

      <Section id="security" title="9. Security">
        <p>
          We use encrypted connections (HTTPS), database rules that let each user read only
          their own data, and an isolated sandbox for the code that builds your parts. No
          system is perfectly secure. If a breach of our security creates a real risk of
          significant harm to you, we will tell you as soon as possible, report it to the
          Office of the Privacy Commissioner of Canada, and inform other authorities as
          the law requires. We keep a record of every breach.
        </p>
      </Section>

      <Section id="children" title="10. Children">
        <p>
          Nfinit is not for children under {minimumAge}. We do not knowingly collect
          personal data from children under {minimumAge}. If you think a child under{" "}
          {minimumAge} has given us personal data, email us and we will delete it.
        </p>
      </Section>

      <Section id="changes" title="11. Changes to this policy">
        <p>
          If we change this policy, we will update the date at the top of this page. If a
          change is important, we will tell you by email or in the studio before it
          applies.
        </p>
      </Section>

      <Section id="contact" title="12. Contact">
        <p>
          {operator}, privacy officer
          <br />
          {location}
          <br />
          Email: <a href={mail}>{contactEmail}</a>
        </p>
      </Section>
    </LegalPage>
  );
}
