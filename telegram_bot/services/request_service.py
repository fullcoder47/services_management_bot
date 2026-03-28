from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from xml.sax.saxutils import escape as xml_escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Request, RequestStatus, User, UserLanguage, UserRole
from services.i18n import t


class RequestServiceError(Exception):
    pass


class RequestNotFoundError(RequestServiceError):
    pass


class RequestAccessDeniedError(RequestServiceError):
    pass


class RequestValidationError(RequestServiceError):
    pass


class RequestStateError(RequestServiceError):
    pass


@dataclass(slots=True)
class CreateRequestDTO:
    user_id: int
    company_id: int
    phone: str
    problem_text: str
    address: str
    problem_image: str | None = None


@dataclass(slots=True)
class CompleteRequestDTO:
    result_text: str
    result_image: str


class RequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(self, payload: CreateRequestDTO) -> Request:
        phone = payload.phone.strip()
        problem_text = payload.problem_text.strip()
        address = payload.address.strip()
        problem_image = payload.problem_image.strip() if isinstance(payload.problem_image, str) else None

        if not phone:
            raise RequestValidationError("Telefon raqami majburiy.")
        if not problem_text:
            raise RequestValidationError("Muammo tavsifi majburiy.")
        if not address:
            raise RequestValidationError("Manzil majburiy.")

        request = Request(
            user_id=payload.user_id,
            company_id=payload.company_id,
            phone=phone,
            problem_text=problem_text,
            address=address,
            problem_image=problem_image or None,
            status=RequestStatus.PENDING,
            result_text=None,
            result_image="",
            completed_at=None,
        )
        self._session.add(request)
        await self._session.commit()
        await self._session.refresh(request)
        return await self.get_request_or_raise(request.id)

    async def get_request(self, request_id: int) -> Request | None:
        statement = (
            select(Request)
            .options(
                selectinload(Request.user),
                selectinload(Request.company),
            )
            .where(Request.id == request_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_request_or_raise(self, request_id: int) -> Request:
        request = await self.get_request(request_id)
        if request is None:
            raise RequestNotFoundError("Ariza topilmadi.")
        return request

    async def get_request_for_user(self, request_id: int, actor: User) -> Request:
        request = await self.get_request_or_raise(request_id)
        if request.user_id != actor.id:
            raise RequestAccessDeniedError("Siz bu arizani ko'ra olmaysiz.")
        return request

    async def list_requests_for_manager(self, actor: User) -> list[Request]:
        self.ensure_can_manage_requests(actor)

        statement = (
            select(Request)
            .options(
                selectinload(Request.user),
                selectinload(Request.company),
            )
            .order_by(Request.created_at.desc(), Request.id.desc())
        )

        if not actor.is_super_admin:
            if actor.company_id is None:
                return []
            statement = statement.where(Request.company_id == actor.company_id)

        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_user_requests(self, user_id: int) -> list[Request]:
        statement = (
            select(Request)
            .options(selectinload(Request.company))
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc(), Request.id.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def export_requests_to_excel(self, actor: User) -> bytes:
        self.ensure_can_export_requests(actor)
        requests = await self.list_requests_for_manager(actor)
        return self._build_requests_excel(requests, actor.ui_language)

    async def get_management_recipients(self, company_id: int) -> list[User]:
        statement = (
            select(User)
            .where(
                User.company_id == company_id,
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            )
            .order_by(User.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_in_progress(self, request_id: int, actor: User) -> Request:
        request = await self.get_request_or_raise(request_id)
        self.ensure_management_access(actor, request)

        if request.status == RequestStatus.DONE:
            raise RequestStateError("Bajarilgan arizani qayta qabul qilib bo'lmaydi.")

        if request.status != RequestStatus.IN_PROGRESS:
            request.status = RequestStatus.IN_PROGRESS
            await self._session.commit()
            await self._session.refresh(request)

        return await self.get_request_or_raise(request.id)

    async def complete_request(
        self,
        request_id: int,
        actor: User,
        payload: CompleteRequestDTO,
    ) -> Request:
        request = await self.get_request_or_raise(request_id)
        self.ensure_management_access(actor, request)

        result_text = payload.result_text.strip()
        result_image = payload.result_image.strip()

        if not result_text:
            raise RequestValidationError("Bajarilgan ish tavsifi majburiy.")
        if not result_image:
            raise RequestValidationError("Bajarilgan ish rasmi majburiy.")
        if request.status == RequestStatus.DONE:
            raise RequestStateError("Bu ariza allaqachon bajarilgan.")

        request.status = RequestStatus.DONE
        request.result_text = result_text
        request.result_image = result_image
        request.completed_at = self._utcnow()

        await self._session.commit()
        await self._session.refresh(request)
        return await self.get_request_or_raise(request.id)

    def ensure_can_manage_requests(self, actor: User) -> None:
        if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR}:
            raise RequestAccessDeniedError("Bu bo'lim faqat super admin, admin va operator uchun.")

    def ensure_management_access(self, actor: User, request: Request) -> None:
        self.ensure_can_manage_requests(actor)
        if actor.is_super_admin:
            return
        if actor.company_id is None or request.company_id != actor.company_id:
            raise RequestAccessDeniedError("Siz bu arizani boshqara olmaysiz.")

    def ensure_can_export_requests(self, actor: User) -> None:
        if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
            raise RequestAccessDeniedError("Excel eksport faqat super admin va admin uchun.")

    @staticmethod
    def format_status(status: RequestStatus, language: UserLanguage | None = None) -> str:
        if status == RequestStatus.PENDING:
            return t(language, "request_status_pending")
        if status == RequestStatus.IN_PROGRESS:
            return t(language, "request_status_progress")
        return t(language, "request_status_done")

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @classmethod
    def _build_requests_excel(
        cls,
        requests: list[Request],
        language: UserLanguage | None = None,
    ) -> bytes:
        rows = [
            [
                "ID",
                "Status",
                "Kompaniya",
                "User",
                "Telefon",
                "Muammo",
                "Manzil",
                "Rasm",
                "Yakuniy izoh",
                "Yakunlangan",
                "Yaratilgan",
            ]
        ]

        for request in requests:
            company_name = request.company.name if request.company is not None else "Noma'lum kompaniya"
            user_name = request.user.display_name if request.user is not None else "Noma'lum user"
            rows.append(
                [
                    str(request.id),
                    cls.format_status(request.status, language),
                    company_name,
                    user_name,
                    request.phone,
                    request.problem_text,
                    request.address,
                    "Bor" if request.problem_image else "Yo'q",
                    request.result_text or "",
                    cls._format_datetime(request.completed_at),
                    cls._format_datetime(request.created_at),
                ]
            )

        return cls._create_xlsx("Arizalar", rows)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def _create_xlsx(cls, sheet_name: str, rows: list[list[str]]) -> bytes:
        sheet_xml = cls._build_sheet_xml(rows)
        workbook_xml = cls._build_workbook_xml(sheet_name)

        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "docProps/app.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>""",
            )
            archive.writestr(
                "docProps/core.xml",
                f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:dcmitype="http://purl.org/dc/dcmitype/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(UTC).isoformat()}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{datetime.now(UTC).isoformat()}</dcterms:modified>
</cp:coreProperties>""",
            )
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/styles.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1">
    <font>
      <sz val="11"/>
      <name val="Calibri"/>
    </font>
  </fonts>
  <fills count="1">
    <fill>
      <patternFill patternType="none"/>
    </fill>
  </fills>
  <borders count="1">
    <border>
      <left/><right/><top/><bottom/><diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>""",
            )
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        return output.getvalue()

    @staticmethod
    def _build_workbook_xml(sheet_name: str) -> str:
        safe_sheet_name = xml_escape(sheet_name)
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{safe_sheet_name}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

    @classmethod
    def _build_sheet_xml(cls, rows: list[list[str]]) -> str:
        row_xml: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cell_xml: list[str] = []
            for column_index, value in enumerate(row, start=1):
                cell_ref = f"{cls._column_letter(column_index)}{row_index}"
                escaped_value = xml_escape(str(value))
                cell_xml.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escaped_value}</t></is></c>'
                )
            row_xml.append(f'<row r="{row_index}">{"".join(cell_xml)}</row>')

        return (
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>"""
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            + "".join(row_xml)
            + "</sheetData></worksheet>"
        )

    @staticmethod
    def _column_letter(index: int) -> str:
        letters = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters
